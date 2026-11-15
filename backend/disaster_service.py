"""Global, best-effort farm hazard screening and public alert aggregation.

Forecast-derived hazard levels are screening signals, not official warnings.
Only source-issued public alerts retain their source severity in the result.
"""

from __future__ import annotations

import asyncio
import math
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from time import monotonic
from typing import Any

import httpx

from .rotation_engine import CROPS
from .soil_profile_service import fetch_soil_profile_async

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"
NWS_URL = "https://api.weather.gov/alerts/active"
LEVELS = {"Safe": 0, "Watch": 1, "Warning": 2, "Critical": 3}
_CACHE: dict[tuple[float, float, str, str], tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 900

HAZARD_ACTIONS = {
    "Heavy rain": ["Clear field drains and safe outlets before rain arrives.", "Pause fertilizer and pesticide spraying to reduce wash-off.", "Move harvested produce, seed, and machinery above low areas."],
    "Flood": ["Move people, livestock, fuel, chemicals, and equipment away from flood paths.", "Do not walk or drive through floodwater; follow local evacuation instructions.", "Protect seed and inputs in a raised, dry location."],
    "Landslide": ["Keep people and livestock away from steep saturated slopes and cracks.", "Divert clean runoff around vulnerable slopes without sending it onto neighboring land.", "Follow local evacuation guidance; do not enter a moving slope or debris flow."],
    "Heatwave": ["Irrigate during cooler hours if water is available, prioritizing establishment and flowering.", "Use mulch or temporary shade for sensitive crops and young transplants.", "Avoid spraying during peak heat and check workers and livestock frequently."],
    "Drought": ["Check root-zone moisture before irrigating and prioritize critical growth stages.", "Reduce evaporation with mulch and control competing weeds.", "Avoid fertilizer application to moisture-stressed crops unless locally advised."],
    "Severe storm": ["Secure lightweight irrigation lines, covers, tools, and stored inputs.", "Move workers and livestock to sturdy shelter; avoid exposed trees and structures.", "Use official local warnings for lightning, wind, and evacuation decisions."],
    "Frost": ["Protect sensitive seedlings and flowers with locally suitable covers.", "Delay irrigation or field work only if local crop guidance recommends it.", "Check low-lying parts of the field first; cold air pools in depressions."],
}


def _empty(name: str, url: str) -> dict[str, Any]:
    return {"status": "unavailable", "provider": name, "source_url": url, "error": None}


async def _json_get(client: httpx.AsyncClient, url: str, *, params: dict[str, Any] | None = None, timeout: float = 7.0) -> dict[str, Any]:
    response = await client.get(url, params=params, timeout=httpx.Timeout(timeout, connect=2.5))
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("provider returned a non-object JSON payload")
    return payload


async def _weather(client: httpx.AsyncClient, lat: float, lon: float) -> dict[str, Any]:
    params = {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 7,
        "daily": "precipitation_sum,precipitation_probability_max,temperature_2m_max,temperature_2m_min,wind_speed_10m_max,wind_gusts_10m_max,et0_fao_evapotranspiration,weather_code",
        "hourly": "precipitation,soil_moisture_0_to_7cm,soil_moisture_28_to_100cm,temperature_2m,wind_gusts_10m",
        "current": "soil_moisture_0_to_7cm,soil_moisture_28_to_100cm",
    }
    try:
        data = await _json_get(client, WEATHER_URL, params=params)
        daily, hourly = data.get("daily", {}), data.get("hourly", {})
        dates = daily.get("time", [])
        day_rows = []
        for index, day in enumerate(dates[:7]):
            row: dict[str, Any] = {"date": day}
            for key in ("precipitation_sum", "precipitation_probability_max", "temperature_2m_max", "temperature_2m_min", "wind_speed_10m_max", "wind_gusts_10m_max", "et0_fao_evapotranspiration", "weather_code"):
                values = daily.get(key, [])
                row[key] = values[index] if index < len(values) else None
            day_rows.append(row)
        times = hourly.get("time", [])
        by_date: dict[str, dict[str, list[float]]] = {}
        for key in ("precipitation", "soil_moisture_0_to_7cm", "soil_moisture_28_to_100cm", "temperature_2m", "wind_gusts_10m"):
            for timestamp, value in zip(times, hourly.get(key, [])):
                if isinstance(value, (int, float)) and math.isfinite(value):
                    by_date.setdefault(timestamp[:10], {}).setdefault(key, []).append(float(value))
        for row in day_rows:
            values = by_date.get(row["date"], {})
            row["rain_24h_mm"] = sum(values.get("precipitation", []))
            row["surface_moisture"] = (sum(values["soil_moisture_0_to_7cm"]) / len(values["soil_moisture_0_to_7cm"])) if values.get("soil_moisture_0_to_7cm") else None
            row["root_moisture"] = (sum(values["soil_moisture_28_to_100cm"]) / len(values["soil_moisture_28_to_100cm"])) if values.get("soil_moisture_28_to_100cm") else None
        return {"status": "available" if day_rows else "partial", "provider": "Open-Meteo weather forecast", "source_url": WEATHER_URL, "timezone": data.get("timezone"), "daily": day_rows, "current_soil_moisture": data.get("current", {}), "elevation_m": data.get("elevation")}
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        return {**_empty("Open-Meteo weather forecast", WEATHER_URL), "error": str(exc)[:180], "daily": [], "current_soil_moisture": {}}


async def _flood(client: httpx.AsyncClient, lat: float, lon: float) -> dict[str, Any]:
    try:
        data = await _json_get(client, FLOOD_URL, params={"latitude": lat, "longitude": lon, "daily": "river_discharge", "past_days": 30, "forecast_days": 7, "timezone": "GMT"})
        daily = data.get("daily", {})
        rows = [{"date": day, "river_discharge_m3_s": value} for day, value in zip(daily.get("time", []), daily.get("river_discharge", []))]
        return {"status": "available" if rows else "partial", "provider": "Open-Meteo Global Flood API / GloFAS", "source_url": FLOOD_URL, "daily": rows}
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        return {**_empty("Open-Meteo Global Flood API / GloFAS", FLOOD_URL), "error": str(exc)[:180], "daily": []}


async def _terrain(client: httpx.AsyncClient, lat: float, lon: float) -> dict[str, Any]:
    # Five GLO-90 samples approximate local relief across ~220 m, not a survey.
    lat_delta = 0.001
    lon_delta = 0.001 / max(math.cos(math.radians(lat)), 0.15)
    points = [(lat, lon), (min(90, lat + lat_delta), lon), (max(-90, lat - lat_delta), lon), (lat, min(180, lon + lon_delta)), (lat, max(-180, lon - lon_delta))]
    params = {"latitude": ",".join(f"{p[0]:.6f}" for p in points), "longitude": ",".join(f"{p[1]:.6f}" for p in points)}
    try:
        data = await _json_get(client, ELEVATION_URL, params=params)
        values = data.get("elevation", [])
        if len(values) != 5 or any(not isinstance(value, (int, float)) for value in values):
            raise ValueError("elevation response did not include all five samples")
        north_south = (float(values[1]) - float(values[2])) / (2 * 111.0)
        east_west = (float(values[3]) - float(values[4])) / (2 * 111.0 * max(math.cos(math.radians(lat)), 0.15))
        slope = math.degrees(math.atan(math.hypot(north_south, east_west)))
        return {"status": "available", "provider": "Open-Meteo Elevation / Copernicus GLO-90", "source_url": ELEVATION_URL, "elevation_m": round(float(values[0]), 1), "estimated_slope_degrees": round(slope, 1), "resolution_m": 90, "note": "Terrain screening estimate from five DEM samples; not a landslide map."}
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        return {**_empty("Open-Meteo Elevation / Copernicus GLO-90", ELEVATION_URL), "error": str(exc)[:180]}


def _geometry_point(geometry: dict[str, Any]) -> tuple[float, float] | None:
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "Point" and isinstance(coordinates, list) and len(coordinates) >= 2:
        return float(coordinates[1]), float(coordinates[0])
    if geometry.get("type") == "Polygon" and coordinates and coordinates[0]:
        ring = coordinates[0]
        return sum(float(p[1]) for p in ring) / len(ring), sum(float(p[0]) for p in ring) / len(ring)
    if geometry.get("type") == "MultiPolygon" and coordinates and coordinates[0] and coordinates[0][0]:
        ring = coordinates[0][0]
        return sum(float(p[1]) for p in ring) / len(ring), sum(float(p[0]) for p in ring) / len(ring)
    return None


def _distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius = 6371.0
    dlat, dlon = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a_lat)) * math.cos(math.radians(b_lat)) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.asin(min(1, math.sqrt(h)))


async def _gdacs(client: httpx.AsyncClient, lat: float, lon: float) -> dict[str, Any]:
    today = date.today()
    start = today - timedelta(days=30)
    try:
        data = await _json_get(client, GDACS_URL, params={"eventlist": "FL;TC;DR;WF;EQ", "fromdate": start.isoformat(), "todate": today.isoformat(), "alertlevel": "red;orange;green"}, timeout=8)
        features = data.get("features", []) if isinstance(data.get("features"), list) else []
        events = []
        for feature in features:
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties", {})
            point = _geometry_point(feature.get("geometry") or {})
            if point is None:
                continue
            distance = _distance_km(lat, lon, *point)
            if distance > 300:
                continue
            raw_level = str(props.get("alertlevel", props.get("alertLevel", "green"))).lower()
            severity = {"red": "Critical", "orange": "Warning", "green": "Watch"}.get(raw_level, "Watch")
            events.append({"id": str(feature.get("id", props.get("eventid", "gdacs"))), "title": str(props.get("name", props.get("eventname", "GDACS disaster event"))), "hazard": str(props.get("eventtype", props.get("event", "Disaster"))), "severity": severity, "distance_km": round(distance), "source": "GDACS", "url": props.get("url", props.get("htmllink")), "issued_at": props.get("fromdate"), "description": props.get("alertscore", "Global event alert; check GDACS for impact details.")})
        return {"status": "available", "provider": "GDACS", "source_url": "https://www.gdacs.org/", "events": events}
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        return {**_empty("GDACS", GDACS_URL), "error": str(exc)[:180], "events": []}


async def _eonet(client: httpx.AsyncClient, lat: float, lon: float) -> dict[str, Any]:
    try:
        data = await _json_get(client, EONET_URL, params={"status": "open", "days": 30, "limit": 500}, timeout=8)
        events = []
        for event in data.get("events", []):
            if not isinstance(event, dict):
                continue
            geometries = event.get("geometry") or []
            points = [_geometry_point(item) for item in geometries if isinstance(item, dict)]
            points = [point for point in points if point]
            if not points:
                continue
            distance = min(_distance_km(lat, lon, *point) for point in points)
            if distance > 250:
                continue
            cats = event.get("categories") or []
            category = str(cats[0].get("title", "Natural event")) if cats and isinstance(cats[0], dict) else "Natural event"
            events.append({"id": str(event.get("id", "eonet")), "title": str(event.get("title", category)), "hazard": category, "severity": "Watch", "distance_km": round(distance), "source": "NASA EONET", "url": event.get("link") or "https://eonet.gsfc.nasa.gov/", "issued_at": geometries[-1].get("date") if geometries else None, "description": event.get("description") or "NASA-curated natural event near this location."})
        return {"status": "available", "provider": "NASA EONET v3", "source_url": "https://eonet.gsfc.nasa.gov/", "events": events}
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        return {**_empty("NASA EONET v3", EONET_URL), "error": str(exc)[:180], "events": []}


async def _nws(client: httpx.AsyncClient, lat: float, lon: float, country: str) -> dict[str, Any]:
    if country != "US":
        return {"status": "not_applicable", "provider": "NOAA / NWS", "source_url": "https://www.weather.gov/", "events": [], "message": "NWS CAP alerts cover the United States only."}
    try:
        data = await _json_get(client, NWS_URL, params={"point": f"{lat},{lon}"}, timeout=6)
        events = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            severity = {"extreme": "Critical", "severe": "Warning", "moderate": "Watch", "minor": "Watch"}.get(str(props.get("severity", "")).lower(), "Watch")
            events.append({"id": str(props.get("id", feature.get("id", "nws"))), "title": props.get("headline") or props.get("event") or "NWS alert", "hazard": props.get("event", "Severe weather"), "severity": severity, "source": "NOAA / NWS CAP", "url": props.get("@id"), "issued_at": props.get("effective"), "arrival": props.get("onset"), "ends_at": props.get("ends"), "description": props.get("description") or "Official National Weather Service alert.", "instruction": props.get("instruction"), "area": props.get("areaDesc")})
        return {"status": "available", "provider": "NOAA / NWS CAP", "source_url": "https://api.weather.gov/alerts/active", "events": events}
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        return {**_empty("NOAA / NWS CAP", NWS_URL), "error": str(exc)[:180], "events": []}


def _tag(element: ET.Element, local_name: str) -> str | None:
    child = next((node for node in element.iter() if node.tag.rsplit("}", 1)[-1] == local_name), None)
    return child.text.strip() if child is not None and child.text else None


async def _configured_cap(client: httpx.AsyncClient, country: str) -> dict[str, Any]:
    # Optional adapter: set ORBIT_CAP_FEED_URL_<ISO2> to a trusted regional
    # CAP Atom/RSS feed. No endpoint is guessed for countries without one.
    url = os.getenv(f"ORBIT_CAP_FEED_URL_{country}") if country else None
    if not url:
        return {"status": "not_configured", "provider": f"Regional CAP feed ({country or 'unknown country'})", "source_url": None, "events": [], "message": "No regional CAP feed URL is configured for this country. Add an official feed with ORBIT_CAP_FEED_URL_<ISO2>."}
    try:
        response = await client.get(url, timeout=httpx.Timeout(6.0, connect=2.5))
        response.raise_for_status()
        root = ET.fromstring(response.content)
        events = []
        for entry in [item for item in root.iter() if item.tag.rsplit("}", 1)[-1] in {"entry", "alert"}]:
            title = _tag(entry, "title") or _tag(entry, "event") or "Regional CAP alert"
            level = (_tag(entry, "severity") or "Moderate").lower()
            severity = "Critical" if level in {"extreme", "red"} else "Warning" if level in {"severe", "orange"} else "Watch"
            link_node = next((item for item in entry if item.tag.rsplit("}", 1)[-1] == "link"), None)
            events.append({"id": _tag(entry, "identifier") or title, "title": title, "hazard": _tag(entry, "event") or title, "severity": severity, "source": f"Regional CAP ({country})", "url": (link_node.attrib.get("href") if link_node is not None else url), "issued_at": _tag(entry, "sent") or _tag(entry, "updated"), "description": _tag(entry, "description") or _tag(entry, "summary") or "Official regional alert."})
        return {"status": "available", "provider": f"Regional CAP ({country})", "source_url": url, "events": events}
    except (httpx.HTTPError, ET.ParseError, ValueError, TypeError) as exc:
        return {**_empty(f"Regional CAP ({country})", url), "error": str(exc)[:180], "events": []}


def _severity_for_weather(daily: list[dict[str, Any]], soil: dict[str, Any], terrain: dict[str, Any], flood: dict[str, Any], crop: dict[str, Any] | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    alerts: list[dict[str, Any]] = []
    timeline = []
    top = (soil.get("depths") or {}).get("0-5cm", {})
    saturation = top.get("field_capacity_m3_m3")
    top_moisture = None
    root_moisture = None
    crop_temp_high = (crop or {}).get("temp", (None, None))[1] if crop and (crop or {}).get("temp") else None
    if daily:
        top_moisture = daily[0].get("surface_moisture")
        root_moisture = daily[0].get("root_moisture")
    today = date.today().isoformat()
    history = [float(row["river_discharge_m3_s"]) for row in flood.get("daily", []) if row.get("date", "") < today and isinstance(row.get("river_discharge_m3_s"), (int, float))]
    forecast_discharge = [row for row in flood.get("daily", []) if row.get("date", "") >= today and isinstance(row.get("river_discharge_m3_s"), (int, float))]
    hist_sorted = sorted(history)
    p90 = hist_sorted[min(len(hist_sorted)-1, int(len(hist_sorted)*0.9))] if hist_sorted else None
    flood_spike = bool(forecast_discharge and p90 is not None and max(float(row["river_discharge_m3_s"]) for row in forecast_discharge) > max(1.0, p90 * 1.5))
    slope = terrain.get("estimated_slope_degrees")
    moist_saturated = top_moisture is not None and (top_moisture >= max(0.38, (saturation + 0.08) if saturation is not None else 0.38))
    rolling3: list[float] = []
    for index in range(len(daily)):
        rolling3.append(sum(float(item.get("precipitation_sum") or 0) for item in daily[index:index+3]))

    heat_limit = (float(crop_temp_high) + 3) if crop_temp_high is not None else 38.0
    hot_indices = {index for index, row in enumerate(daily) if isinstance(row.get("temperature_2m_max"), (int, float)) and row["temperature_2m_max"] >= heat_limit}
    heatwave_indices: set[int] = set()
    for index in hot_indices:
        run = {index}
        cursor = index - 1
        while cursor in hot_indices:
            run.add(cursor); cursor -= 1
        cursor = index + 1
        while cursor in hot_indices:
            run.add(cursor); cursor += 1
        if len(run) >= 3:
            heatwave_indices.update(run)

    dry_indices = {
        index for index, row in enumerate(daily)
        if float(row.get("precipitation_sum") or 0) <= 1
        and isinstance(row.get("et0_fao_evapotranspiration"), (int, float))
        and row["et0_fao_evapotranspiration"] >= 4
    }
    drought_indices: set[int] = set()
    for index in dry_indices:
        run = {index}
        cursor = index - 1
        while cursor in dry_indices:
            run.add(cursor); cursor -= 1
        cursor = index + 1
        while cursor in dry_indices:
            run.add(cursor); cursor += 1
        if len(run) >= 3:
            drought_indices.update(run)

    def add(hazard: str, severity: str, detail: str, arrival: str | None, source: str = "Open-Meteo forecast", confidence: str = "screening"):
        alerts.append({"id": f"{hazard.lower().replace(' ', '-')}-{arrival or 'active'}", "hazard": hazard, "title": hazard, "severity": severity, "detail": detail, "arrival": arrival, "source": source, "confidence": confidence, "actions": HAZARD_ACTIONS.get(hazard, [])})

    for index, row in enumerate(daily):
        rain = float(row.get("precipitation_sum") or 0)
        rain72 = rolling3[index] if index < len(rolling3) else rain
        temp_high = row.get("temperature_2m_max")
        temp_low = row.get("temperature_2m_min")
        wind = max(float(row.get("wind_gusts_10m_max") or 0), float(row.get("wind_speed_10m_max") or 0))
        root = row.get("root_moisture")
        et0 = row.get("et0_fao_evapotranspiration")
        risks: dict[str, str] = {}
        risks["Rain"] = "Critical" if rain >= 120 else "Warning" if rain >= 75 else "Watch" if rain >= 40 else "Safe"
        if moist_saturated and rain >= 25 and index == 0 and LEVELS[risks["Rain"]] < 2:
            risks["Rain"] = "Warning"
        risks["Flood"] = "Warning" if flood_spike and index < 7 else "Watch" if rain72 >= 100 else "Safe"
        landslide_risk = (slope is not None and slope >= 15 and rain72 >= 60 and ((root is not None and root >= 0.35) or moist_saturated))
        risks["Landslide"] = "Critical" if landslide_risk and rain72 >= 120 else "Warning" if landslide_risk else "Watch" if slope is not None and slope >= 15 and rain72 >= 40 else "Safe"
        risks["Heatwave"] = "Critical" if index in heatwave_indices and temp_high is not None and temp_high >= (crop_temp_high + 5 if crop_temp_high is not None else 42) else "Warning" if index in heatwave_indices else "Watch" if index in hot_indices or temp_high is not None and temp_high >= 35 else "Safe"
        risks["Drought"] = "Warning" if index in drought_indices and root is not None and root < 0.15 else "Watch" if index in drought_indices else "Safe"
        risks["Severe storm"] = "Critical" if wind >= 100 else "Warning" if wind >= 75 else "Watch" if wind >= 55 else "Safe"
        risks["Frost"] = "Warning" if temp_low is not None and temp_low <= 0 else "Watch" if temp_low is not None and temp_low <= 4 else "Safe"
        timeline.append({"date": row.get("date"), "rain_mm": round(rain, 1), "rain72_mm": round(rain72, 1), "temp_max_c": temp_high, "temp_min_c": temp_low, "wind_gust_kmh": wind, "et0_mm": et0, "risks": risks})

    for hazard, metric, units in (("Heavy rain", "precipitation_sum", "mm/day"), ("Heatwave", "temperature_2m_max", "°C"), ("Severe storm", "wind_gusts_10m_max", "km/h")):
        candidates = [(row, row.get(metric)) for row in daily if isinstance(row.get(metric), (int, float))]
        if not candidates:
            continue
        row, value = max(candidates, key=lambda item: item[1])
        severity = next((item["risks"][{"Heavy rain":"Rain", "Heatwave":"Heatwave", "Severe storm":"Severe storm"}[hazard]] for item in timeline if item["date"] == row["date"]), "Safe")
        if LEVELS.get(severity, 0) >= 1:
            add(hazard, severity, f"Forecast peak {value:g} {units} on {row['date']}.", row["date"])
    if flood_spike:
        peak = max(forecast_discharge, key=lambda row: float(row["river_discharge_m3_s"]))
        value = float(peak["river_discharge_m3_s"])
        add("Flood", "Warning", f"Forecast discharge reaches {value:.1f} m³/s, above the recent local model baseline ({p90:.1f} m³/s). The nearest modeled river may be several kilometres away.", peak["date"], "Open-Meteo GloFAS", "model anomaly")
    if any(day["risks"]["Landslide"] != "Safe" for day in timeline):
        day = next(day for day in timeline if day["risks"]["Landslide"] != "Safe")
        add("Landslide", day["risks"]["Landslide"], f"{day['rain72_mm']:.1f} mm forecast over a 3-day window with estimated slope {slope:.1f}° and wet soil signal.", day["date"], "Open-Meteo + Copernicus DEM", "terrain/rainfall screening")
    for hazard in ("Drought", "Frost"):
        if any(day["risks"][hazard] != "Safe" for day in timeline):
            day = next(day for day in timeline if day["risks"][hazard] != "Safe")
            add(hazard, day["risks"][hazard], f"Forecast conditions meet the {hazard.lower()} screening threshold on {day['date']}.", day["date"])
    if moist_saturated:
        add("Waterlogging", "Warning", f"Modeled surface soil moisture is {top_moisture:.2f} m³/m³, near saturation for the mapped topsoil.", today, "Open-Meteo soil moisture", "model screening")
    return {"daily": timeline, "surface_moisture_m3_m3": top_moisture, "root_moisture_m3_m3": root_moisture, "slope_degrees": slope, "river_discharge_baseline_p90_m3_s": p90}, alerts


def _official_to_alert(event: dict[str, Any]) -> dict[str, Any]:
    hazard = str(event.get("hazard", "")).lower()
    mapped = "Flood" if "flood" in hazard or hazard in {"fl", "floods"} else "Landslide" if "landslide" in hazard else "Severe storm" if any(term in hazard for term in ("storm", "cyclone", "tropical")) else "Drought" if "drought" in hazard else event.get("title", "Official hazard")
    return {**event, "hazard": mapped, "title": event.get("title") or mapped, "detail": event.get("description") or "Official public hazard event near the selected farm.", "arrival": event.get("arrival") or event.get("issued_at"), "confidence": "official feed", "actions": HAZARD_ACTIONS.get(mapped, ["Follow instructions from the issuing emergency authority."])}


def _helpline(country: str) -> dict[str, str | None]:
    if country == "IN":
        return {"name": "India emergency services", "number": "112", "source_url": "https://www.mha.gov.in/emergency-response-support-system-erss"}
    if country == "US":
        return {"name": "United States emergency services", "number": "911", "source_url": "https://www.911.gov/calling-911/"}
    return {"name": "Local emergency services", "number": None, "source_url": None}


async def get_disaster_alerts(latitude: float, longitude: float, crop_name: str | None = None, country_code: str | None = None) -> dict[str, Any]:
    """Aggregate global forecasts, hazard events, terrain and optional CAP alerts."""
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("latitude and longitude must be within WGS84 bounds")
    country = (country_code or "").upper()
    normalized_crop = (crop_name or "").casefold()
    cache_key = (round(latitude, 3), round(longitude, 3), normalized_crop, country)
    cached = _CACHE.get(cache_key)
    if cached and cached[0] > monotonic():
        return {**cached[1], "cache": {"hit": True, "ttl_seconds": round(cached[0] - monotonic())}}
    headers = {"User-Agent": "Orbit_crop/1.0 (global agricultural hazard screening; contact: project maintainers)", "Accept": "application/geo+json, application/json, application/atom+xml, application/xml"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=2.5), follow_redirects=True, headers=headers) as client:
        tasks = await asyncio.gather(_weather(client, latitude, longitude), _flood(client, latitude, longitude), _terrain(client, latitude, longitude), _gdacs(client, latitude, longitude), _eonet(client, latitude, longitude), _nws(client, latitude, longitude, country), _configured_cap(client, country), fetch_soil_profile_async(client, latitude, longitude), return_exceptions=True)
    names = ("weather", "flood", "terrain", "gdacs", "eonet", "nws", "cap", "soil")
    fallback = {"weather": _empty("Open-Meteo weather forecast", WEATHER_URL), "flood": _empty("Open-Meteo Global Flood API / GloFAS", FLOOD_URL), "terrain": _empty("Open-Meteo Elevation / Copernicus GLO-90", ELEVATION_URL), "gdacs": _empty("GDACS", GDACS_URL), "eonet": _empty("NASA EONET v3", EONET_URL), "nws": _empty("NOAA / NWS", NWS_URL), "cap": _empty("Regional CAP", ""), "soil": {"status": "unavailable", "depths": {}}}
    data = {name: (fallback[name] if isinstance(value, BaseException) else value) for name, value in zip(names, tasks)}
    crop = next((info for name, info in CROPS.items() if name.casefold() == normalized_crop), None)
    conditions, forecast_alerts = _severity_for_weather(data["weather"].get("daily", []), data["soil"], data["terrain"], data["flood"], crop)
    official = [_official_to_alert(event) for source in ("nws", "cap", "gdacs", "eonet") for event in data[source].get("events", [])]
    # Keep official alerts separate in origin metadata, but present them together.
    alerts = forecast_alerts + official
    alerts.sort(key=lambda item: (-LEVELS.get(item.get("severity", "Watch"), 1), item.get("arrival") or "9999"))
    active = [item for item in alerts if LEVELS.get(item.get("severity", "Safe"), 0) >= 1]
    sources = {name: {"status": value.get("status", "unavailable"), "provider": value.get("provider"), "error": value.get("error"), "message": value.get("message")} for name, value in data.items()}
    result = {
        "location": {"latitude": latitude, "longitude": longitude, "country_code": country or None},
        "generated_at": datetime.now(timezone.utc).isoformat(), "expires_in_seconds": _CACHE_TTL,
        "overall_level": max((item["severity"] for item in active), key=lambda level: LEVELS.get(level, 0), default="Safe"),
        "active_count": len(active), "alerts": active, "timeline": conditions["daily"],
        "conditions": {key: value for key, value in conditions.items() if key != "daily"},
        "sources": sources, "helpline": _helpline(country),
        "country_alert_note": "US National Weather Service CAP alerts are connected." if country == "US" else sources["cap"].get("message") or ("No country-specific CAP connector is configured; global sources and forecast screening remain active." if country != "US" else ""),
        "caveat": "Forecast-derived Watch/Warning/Critical labels are transparent screening thresholds, not official warnings or a substitute for local emergency services. Check source alerts and local authorities before acting.",
        "attribution": ["Open-Meteo weather and flood forecast", "GDACS", "NASA EONET", "Copernicus GLO-90 via Open-Meteo Elevation", "ISRIC SoilGrids"],
    }
    _CACHE[cache_key] = (monotonic() + _CACHE_TTL, result)
    return {**result, "cache": {"hit": False, "ttl_seconds": _CACHE_TTL}}
