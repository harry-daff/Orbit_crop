"""NASA POWER clients for point and field-boundary climate time series."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from math import atan2, cos, radians, sin, sqrt
from typing import Any

import requests

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
AG_PARAMETERS = ("PRECTOTCORR", "T2M", "ALLSKY_SFC_SW_DWN")
HY_PARAMETERS = ("GWETROOT", "GWETTOP")
SMAP_PARAMETERS = ("RZMC", "SFMC")
PARAMETERS = AG_PARAMETERS + HY_PARAMETERS
ALL_DAILY_PARAMETERS = PARAMETERS + SMAP_PARAMETERS
PARAMETER_LABELS = {
    "PRECTOTCORR": "Precipitation (mm/day)",
    "T2M": "Temperature at 2 m (°C)",
    "GWETROOT": "Root-zone soil wetness (fraction)",
    "GWETTOP": "Surface soil wetness (fraction)",
    "ALLSKY_SFC_SW_DWN": "All-sky surface shortwave (kWh/m²/day)",
}


class NasaPowerError(RuntimeError):
    """Raised when NASA POWER data cannot be fetched or parsed."""


def _request_parameters(latitude: float, longitude: float, start: date, end: date, parameters: tuple[str, ...], community: str, session: requests.Session) -> tuple[dict[str, Any], dict[str, Any]]:
    params = {
        "parameters": ",".join(parameters), "community": community,
        "longitude": str(longitude), "latitude": str(latitude),
        "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"),
        "time-standard": "UTC", "format": "JSON",
    }
    response = session.get(POWER_URL, params=params, timeout=(8, 90))
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text[:600].replace("\n", " ")
        raise NasaPowerError(f"NASA POWER {community} request returned HTTP {response.status_code}: {detail}") from exc
    payload = response.json()
    try:
        raw = payload["properties"]["parameter"]
        if not all(key in raw for key in parameters):
            raise ValueError("one or more requested parameters are missing")
        return raw, payload.get("parameters", {})
    except (KeyError, TypeError, ValueError) as exc:
        raise NasaPowerError(f"Unexpected NASA POWER response: {exc}") from exc


def _value_in_kwh(value: float, unit: str) -> float:
    """Normalize shortwave daily energy to kWh/m²/day using response metadata."""
    normalized = unit.lower().replace(" ", "").replace("²", "2")
    if "mj" in normalized:
        return value / 3.6
    # POWER's standard daily solar unit is kW-hr/m^2/day. Treat an absent
    # unit as the documented standard, but surface units in the response.
    return value


def fetch_power_data(
    latitude: float,
    longitude: float,
    years: int = 3,
    *,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Fetch daily weather and hydrology products at an exact coordinate.

    Weather, radiation, and model wetness are requested from the AG endpoint
    when available. A weather-only retry preserves climate planning if the
    API's parameter catalog does not expose wetness for this community.
    """
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("coordinates are outside valid latitude/longitude bounds")
    if not 1 <= years <= 5:
        raise ValueError("years must be between 1 and 5")
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=365 * years - 1)
    client = session or requests.Session()
    try:
        # The current POWER temporal API accepts AG/RE/SB communities. Try
        # wetness with AG first; the HY catalog is not accepted as a temporal
        # API community in some deployments, despite HY parameter metadata.
        try:
            raw, metadata = _request_parameters(latitude, longitude, start, end, PARAMETERS, "AG", client)
            hydrology_status = "available"
            hydrology_error = None
        except NasaPowerError as wetness_error:
            raw, metadata = _request_parameters(latitude, longitude, start, end, AG_PARAMETERS, "AG", client)
            for key in HY_PARAMETERS:
                raw[key] = {}
            hydrology_status = "unavailable"
            hydrology_error = str(wetness_error)
        smap_status = "unavailable"
        smap_error = None
        try:
            smap_raw, _ = _request_parameters(latitude, longitude, start, end, SMAP_PARAMETERS, "AG", client)
            raw.update(smap_raw)
            smap_status = "available" if any(value not in (None, -999) for series in smap_raw.values() for value in series.values()) else "unavailable"
        except (NasaPowerError, requests.RequestException, ValueError, TypeError) as error:
            for key in SMAP_PARAMETERS:
                raw[key] = {}
            smap_error = str(error)
        daily = []
        for day_key in sorted(raw["T2M"]):
            values = {key: raw.get(key, {}).get(day_key) for key in ALL_DAILY_PARAMETERS}
            if any(values[key] is None or values[key] == -999 for key in AG_PARAMETERS):
                continue
            for key in HY_PARAMETERS + SMAP_PARAMETERS:
                if values[key] == -999:
                    values[key] = None
            solar_unit = str(metadata.get("ALLSKY_SFC_SW_DWN", {}).get("units", "kW-hr/m^2/day"))
            values["ALLSKY_SFC_SW_DWN"] = _value_in_kwh(float(values["ALLSKY_SFC_SW_DWN"]), solar_unit)
            daily.append({"date": f"{day_key[:4]}-{day_key[4:6]}-{day_key[6:]}", **{key: float(value) if value is not None else None for key, value in values.items()}})
        if not daily:
            raise ValueError("NASA returned no complete daily records")
    except (requests.RequestException, ValueError, TypeError) as exc:
        if isinstance(exc, NasaPowerError):
            raise
        raise NasaPowerError(f"NASA POWER request failed: {exc}") from exc

    has_wetness = any(record.get("GWETROOT") is not None for record in daily)

    return {
        "source": "NASA POWER", "source_url": POWER_URL,
        "requested_start": start.isoformat(), "requested_end": end.isoformat(),
        "observed_start": daily[0]["date"], "observed_end": daily[-1]["date"],
        "latitude": latitude, "longitude": longitude, "daily": daily,
        "solar_unit": "kWh/m²/day", "time_standard": "UTC",
        "hydrology_status": "available" if has_wetness else "unavailable",
        "hydrology_error": hydrology_error if hydrology_error or has_wetness else "No valid root-zone wetness observations were returned.",
        "smap_status": smap_status,
        "smap_error": smap_error,
    }


def monthly_climatology(daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return calendar-month averages across all daily records supplied."""
    buckets = {month: {key: [] for key in ALL_DAILY_PARAMETERS} for month in range(1, 13)}
    for record in daily:
        month = int(record["date"][5:7])
        for key in ALL_DAILY_PARAMETERS:
            if record.get(key) is not None:
                buckets[month][key].append(float(record[key]))
    result = []
    for month in range(1, 13):
        values = buckets[month]
        average = lambda key: round(sum(values[key]) / len(values[key]), 3) if values[key] else None
        result.append({
            "month": month, "month_name": date(2000, month, 1).strftime("%b"),
            "rainfall_mm_day": average("PRECTOTCORR"), "temperature_c": average("T2M"),
            "root_zone_wetness": average("GWETROOT"), "surface_wetness": average("GWETTOP"),
            "solar_kwh_m2_day": average("ALLSKY_SFC_SW_DWN"),
            "smap_root_moisture_m3_m3": average("RZMC"), "smap_surface_moisture_m3_m3": average("SFMC"),
        })
    return result


def _perimeter_samples(ring: list[list[float]], limit: int = 8) -> list[tuple[float, float]]:
    """Pick evenly spaced boundary sample coordinates; never substitute a centroid."""
    vertices = ring[:-1] if ring and ring[0] == ring[-1] else ring
    if len(vertices) <= limit:
        return [(float(lat), float(lon)) for lon, lat in vertices]
    lengths = []
    total = 0.0
    for index, (lon1, lat1) in enumerate(vertices):
        lon2, lat2 = vertices[(index + 1) % len(vertices)]
        # Equirectangular edge length is adequate for distributing samples.
        length = sqrt(((lon2 - lon1) * cos(radians((lat1 + lat2) / 2))) ** 2 + (lat2 - lat1) ** 2)
        lengths.append(length); total += length
    samples = []
    for point_index in range(limit):
        target = total * point_index / limit
        for edge_index, length in enumerate(lengths):
            if target <= length:
                lon1, lat1 = vertices[edge_index]
                lon2, lat2 = vertices[(edge_index + 1) % len(vertices)]
                fraction = target / length if length else 0
                samples.append((lat1 + (lat2 - lat1) * fraction, lon1 + (lon2 - lon1) * fraction))
                break
            target -= length
    return samples


def _unique_power_grid_samples(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Avoid duplicate calls for perimeter points that land in one 0.5° POWER cell."""
    seen: set[tuple[int, int]] = set()
    unique = []
    for latitude, longitude in points:
        cell = (int((latitude + 90) * 2), int((longitude + 180) * 2))
        if cell not in seen:
            seen.add(cell)
            unique.append((latitude, longitude))
    return unique


def geodesic_area_hectares(ring: list[list[float]]) -> float:
    """Approximate polygon area on a sphere from GeoJSON [longitude, latitude]."""
    vertices = ring[:-1] if ring and ring[0] == ring[-1] else ring
    earth_radius_m = 6_371_008.8
    area = 0.0
    for index, (lon1, lat1) in enumerate(vertices):
        lon2, lat2 = vertices[(index + 1) % len(vertices)]
        area += radians(lon2 - lon1) * (2 + sin(radians(lat1)) + sin(radians(lat2)))
    return abs(area * earth_radius_m * earth_radius_m / 2) / 10_000


def fetch_field_power_data(latitude: float, longitude: float, years: int = 3, polygon: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch an exact point series or average perimeter point series for a field.

    POWER's temporal point endpoint does not accept GeoJSON. For a drawn
    boundary, sample up to eight points on the perimeter, query each exact
    coordinate, then average valid observations by date. The product grid is
    much coarser than an individual field; this is a field estimate, not
    independent measurements from within the parcel.
    """
    if polygon is None:
        data = fetch_power_data(latitude, longitude, years)
        data["sampling"] = {"method": "exact_coordinate", "coordinates": [[longitude, latitude]]}
        return data
    try:
        ring = polygon["coordinates"][0]
        perimeter_points = _perimeter_samples(ring)
        if len(perimeter_points) < 3:
            raise ValueError("a field boundary must have at least three points")
        points = _unique_power_grid_samples(perimeter_points)
        outputs: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(4, len(points))) as pool:
            futures = [pool.submit(fetch_power_data, lat, lon, years) for lat, lon in points]
            for future in as_completed(futures):
                outputs.append(future.result())
        by_date: dict[str, dict[str, list[float]]] = {}
        for output in outputs:
            for day in output["daily"]:
                target = by_date.setdefault(day["date"], {key: [] for key in ALL_DAILY_PARAMETERS})
                for key in ALL_DAILY_PARAMETERS:
                    if day.get(key) is not None:
                        target[key].append(day[key])
        daily = [{"date": day, **{key: round(sum(values[key]) / len(values[key]), 4) if values[key] else None for key in ALL_DAILY_PARAMETERS}}
                 for day, values in sorted(by_date.items()) if all(values[key] for key in AG_PARAMETERS)]
        if not daily:
            raise ValueError("No overlapping NASA records were returned for the boundary")
        return {
            "source": "NASA POWER", "source_url": POWER_URL,
            "requested_start": min(item["requested_start"] for item in outputs),
            "requested_end": min(item["requested_end"] for item in outputs),
            "observed_start": daily[0]["date"], "observed_end": daily[-1]["date"],
            "latitude": latitude, "longitude": longitude, "daily": daily,
            "solar_unit": "kWh/m²/day", "time_standard": "UTC",
            "hydrology_status": "available" if any(item.get("GWETROOT") is not None for item in daily) else "unavailable",
            "hydrology_error": next((item.get("hydrology_error") for item in outputs if item.get("hydrology_error")), None),
            "smap_status": "available" if any(item.get("smap_status") == "available" for item in outputs) else "unavailable",
            "smap_error": next((item.get("smap_error") for item in outputs if item.get("smap_error")), None),
            "sampling": {"method": "perimeter_multi_point_mean", "coordinates": [[lon, lat] for lat, lon in points], "candidate_points": len(perimeter_points), "unique_grid_samples": len(points), "grid_caveat": "NASA POWER grid cells can overlap for small fields; sample means are not field-scale observations."},
        }
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        if isinstance(exc, NasaPowerError):
            raise
        raise ValueError(f"Invalid field polygon or unable to sample it: {exc}") from exc


def soil_health_status(latitude: float, longitude: float, monthly: list[dict[str, Any]], daily: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Describe available POWER wetness and report unsupported soil texture honestly."""
    latest = next((item for item in reversed(daily or []) if item.get("GWETROOT") is not None), None)
    latest_month = next((item for item in reversed(monthly) if item.get("root_zone_wetness") is not None), None)
    smap_latest = next((item for item in reversed(daily or []) if item.get("RZMC") is not None), None)
    smap_surface = next((item for item in reversed(daily or []) if item.get("SFMC") is not None), None)
    return {
        "provider": "NASA POWER / GEOS model", "status": "available" if latest else "unavailable",
        "latitude": latitude, "longitude": longitude,
        "root_zone_depth": "model root zone; approximately 0–100 cm depending on source model",
        "root_zone_wetness": latest.get("GWETROOT") if latest else latest_month.get("root_zone_wetness") if latest_month else None,
        "surface_wetness": latest.get("GWETTOP") if latest else latest_month.get("surface_wetness") if latest_month else None,
        "smap": {"provider": "NASA SMAP L4 via POWER", "status": "available" if smap_latest else "unavailable", "root_zone_m3_m3": smap_latest.get("RZMC") if smap_latest else None, "surface_m3_m3": smap_surface.get("SFMC") if smap_surface else None, "root_zone_depth": "0–100 cm", "surface_depth": "0–5 cm", "unit": "m³/m³"},
        "message": None if latest or latest_month else "NASA POWER Hydrology wetness values are currently unavailable for this query.",
        "monthly": [{"month": item["month_name"], "root_zone_wetness": item["root_zone_wetness"], "surface_wetness": item["surface_wetness"], "smap_root_moisture_m3_m3": item.get("smap_root_moisture_m3_m3"), "smap_surface_moisture_m3_m3": item.get("smap_surface_moisture_m3_m3")} for item in monthly],
        "texture": {"status": "not_configured", "message": "Sand/silt/clay fractions are not measured by NASA POWER or SMAP moisture products. Connect a soil-profile dataset (for example, SoilGrids) or a field soil test."},
        "ndvi": {"status": "not_configured", "message": "NDVI requires a vegetation reflectance product; NASA POWER does not provide plot-level NDVI."},
    }


def fetch_deeper_soil_metrics(latitude: float, longitude: float) -> dict[str, Any]:
    """Explicit extension point for NASA SMAP/GLDAS authenticated data services."""
    return {
        "status": "not_configured", "provider": "NASA SMAP / GLDAS", "latitude": latitude,
        "longitude": longitude,
        "message": "Configure a NASA Earthdata-backed SMAP/GLDAS adapter for additional moisture products.",
    }
