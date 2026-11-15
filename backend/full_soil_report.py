"""Parallel, cached soil/climate report assembly for exact user coordinates."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, timedelta
from time import monotonic
from typing import Any

import httpx

from .nasa_service import fetch_field_power_data, monthly_climatology
from .soil_profile_service import DEPTHS, SOILGRIDS_URL, fetch_soil_profile_async

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
OPENLANDMAP_WMS = "https://geoserver.opengeohub.org/landgisgeoserver/wms"
MOISTURE_VARIABLES = (
    "soil_moisture_0_to_7cm", "soil_moisture_7_to_28cm",
    "soil_moisture_28_to_100cm", "soil_moisture_100_to_255cm",
)
_REPORT_CACHE: dict[tuple[float, float, int, str], tuple[float, dict[str, Any]]] = {}
_REPORT_LOCKS: dict[tuple[float, float, int, str], asyncio.Lock] = {}


def _moisture_status(value_m3_m3: float | None, field_capacity: float | None, wilting_point: float | None) -> str | None:
    if value_m3_m3 is None:
        return None
    if field_capacity is not None and wilting_point is not None:
        if value_m3_m3 <= wilting_point:
            return "dry"
        if value_m3_m3 >= field_capacity + 0.10:
            return "waterlogged"
        return "optimal"
    # Broad model-based screening thresholds, used only when profile data are absent.
    return "dry" if value_m3_m3 < 0.10 else "waterlogged" if value_m3_m3 > 0.45 else "optimal"


def _profile_threshold(profile: dict[str, Any], depth_candidates: tuple[str, ...], key: str) -> float | None:
    layers = profile.get("depths") or {}
    values = [layers.get(depth, {}).get(key) for depth in depth_candidates]
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


async def _open_meteo(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    params = {
        "latitude": latitude, "longitude": longitude, "current": ",".join(MOISTURE_VARIABLES),
        "hourly": ",".join(MOISTURE_VARIABLES), "forecast_days": 3, "timezone": "auto",
    }
    try:
        response = await client.get(OPEN_METEO_FORECAST, params=params, timeout=httpx.Timeout(7.0, connect=2.5))
        response.raise_for_status()
        payload = response.json()
        current = payload.get("current", {})
        now: dict[str, float | None] = {}
        for variable in MOISTURE_VARIABLES:
            value = current.get(variable)
            now[variable] = float(value) if isinstance(value, (int, float)) else None

        hourly = payload.get("hourly", {})
        times = hourly.get("time", [])
        forecast: dict[str, dict[str, list[float]]] = {}
        for variable in MOISTURE_VARIABLES:
            series = hourly.get(variable, [])
            for timestamp, value in zip(times, series):
                if isinstance(value, (int, float)):
                    forecast.setdefault(timestamp[:10], {}).setdefault(variable, []).append(float(value))
        forecast_daily = []
        for day, values in sorted(forecast.items()):
            forecast_daily.append({"date": day, **{
                variable: round(sum(values[variable]) / len(values[variable]), 4) if values.get(variable) else None
                for variable in MOISTURE_VARIABLES
            }})
        return {
            "status": "available" if any(value is not None for value in now.values()) else "partial",
            "provider": "Open-Meteo forecast models", "source_url": OPEN_METEO_FORECAST,
            "model_run_time": current.get("time"), "unit": payload.get("current_units", {}).get(MOISTURE_VARIABLES[0], "m³/m³"),
            "current_m3_m3": now, "current_percent_vv": {key: round(value * 100, 1) if value is not None else None for key, value in now.items()},
            "forecast_daily": forecast_daily, "grid_resolution_note": "Gridded weather-model soil moisture; not a field sensor.",
        }
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        reason = str(exc).strip() or type(exc).__name__
        return {"status": "unavailable", "provider": "Open-Meteo forecast models", "source_url": OPEN_METEO_FORECAST, "error": reason[:220], "current_m3_m3": {key: None for key in MOISTURE_VARIABLES}, "current_percent_vv": {key: None for key in MOISTURE_VARIABLES}, "forecast_daily": []}


async def _open_meteo_history(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    end = date.today() - timedelta(days=5)  # archive products have a publication delay
    start = end - timedelta(days=29)
    try:
        response = await client.get(OPEN_METEO_ARCHIVE, params={
            "latitude": latitude, "longitude": longitude, "start_date": start.isoformat(), "end_date": end.isoformat(),
            "hourly": ",".join(MOISTURE_VARIABLES), "timezone": "auto", "models": "era5_land",
        }, timeout=httpx.Timeout(8.0, connect=2.5))
        response.raise_for_status()
        payload = response.json()
        hourly = payload.get("hourly", {})
        times = hourly.get("time", [])
        days: dict[str, dict[str, list[float]]] = {}
        for variable in MOISTURE_VARIABLES:
            for timestamp, value in zip(times, hourly.get(variable, [])):
                if isinstance(value, (int, float)):
                    days.setdefault(timestamp[:10], {}).setdefault(variable, []).append(float(value))
        daily = [{"date": day, **{key: round(sum(values.get(key, [])) / len(values[key]), 4) if values.get(key) else None for key in MOISTURE_VARIABLES}} for day, values in sorted(days.items())]
        return {"status": "available" if daily else "unavailable", "provider": "Open-Meteo ERA5-Land archive", "start": start.isoformat(), "end": end.isoformat(), "daily": daily, "unit": "m³/m³"}
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        reason = str(exc).strip() or type(exc).__name__
        return {"status": "unavailable", "provider": "Open-Meteo ERA5-Land archive", "start": start.isoformat(), "end": end.isoformat(), "daily": [], "error": reason[:220]}


async def _openlandmap_water(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    """Optional point sample via OpenLandMap's public GeoServer WMS GetFeatureInfo."""
    # The source is a static 250 m prediction at 0/10/30/60/100/200 cm. The
    # raster service can be intermittent; SoilGrids water-retention estimates
    # remain a separately labeled fallback and are never relabeled as OLM.
    lon_pad = 0.001
    lat_pad = 0.001
    layers = []
    for suction in ("33kpa", "1500kpa"):
        for depth in (0, 10, 30, 60, 100, 200):
            layer_suction = "33kPa" if suction == "33kpa" else "1500kPa"
            layers.append(f"predicted250m:sol_watercontent.{layer_suction}_usda.4b1c_m_250m_b{depth}..{depth}cm_1950..2017_v0.1")
    params = {
        "service": "WMS", "version": "1.1.1", "request": "GetFeatureInfo",
        "layers": ",".join(layers), "query_layers": ",".join(layers), "styles": "",
        "srs": "EPSG:4326", "bbox": f"{longitude-lon_pad},{latitude-lat_pad},{longitude+lon_pad},{latitude+lat_pad}",
        "width": 101, "height": 101, "x": 50, "y": 50, "format": "image/png", "info_format": "application/json", "feature_count": 12,
    }
    try:
        response = await client.get(OPENLANDMAP_WMS, params=params, timeout=httpx.Timeout(5.0, connect=2.0))
        response.raise_for_status()
        payload = response.json()
        results: dict[str, dict[str, float | None]] = {str(depth): {"field_capacity_pct": None, "wilting_point_pct": None} for depth in (0, 10, 30, 60, 100, 200)}
        for feature in payload.get("features", []):
            props = feature.get("properties", {})
            layer_name = str(props.get("layer", props.get("name", feature.get("id", "")))).lower()
            value = next((float(props[key]) for key in ("GRAY_INDEX", "value", "pixel_value") if isinstance(props.get(key), (float, int)) and props[key] >= 0), None)
            if value is None:
                value = next((float(item) for item in props.values() if isinstance(item, (float, int)) and item >= 0), None)
            if value is None:
                continue
            depth = next((str(depth) for depth in (0, 10, 30, 60, 100, 200) if f"b{depth}..{depth}cm" in layer_name), None)
            target = "field_capacity_pct" if "33kpa" in layer_name else "wilting_point_pct" if "1500kpa" in layer_name else None
            if depth and target:
                results[depth][target] = value
        available = any(value[key] is not None for value in results.values() for key in value)
        return {"status": "available" if available else "unavailable", "provider": "OpenLandMap water content", "source_url": OPENLANDMAP_WMS, "resolution_m": 250, "depths_cm": results, "unit": "% v/v", "message": "Static mapped water-retention estimate; not a current water-table measurement." if available else "OpenLandMap point sampling did not return readable raster values."}
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        reason = str(exc).strip() or type(exc).__name__
        return {"status": "unavailable", "provider": "OpenLandMap water content", "source_url": OPENLANDMAP_WMS, "resolution_m": 250, "depths_cm": {}, "error": reason[:180], "message": f"OpenLandMap could not be queried: {reason[:180]}"}


async def _nasa_history(latitude: float, longitude: float, years: int, polygon: dict[str, Any] | None) -> dict[str, Any]:
    try:
        raw = await asyncio.wait_for(asyncio.to_thread(fetch_field_power_data, latitude, longitude, years, polygon), timeout=12.0)
        return {"status": "available", **raw, "monthly": monthly_climatology(raw["daily"])}
    except Exception as exc:
        return {"status": "unavailable", "source": "NASA POWER", "source_url": "https://power.larc.nasa.gov/", "daily": [], "monthly": [], "error": str(exc)[:220]}


async def _collect_external(latitude: float, longitude: float, years: int, polygon: dict[str, Any] | None) -> dict[str, Any]:
    timeout = httpx.Timeout(8.0, connect=2.5)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": "Orbit_crop/1.0 (agriculture planning dashboard)"}) as client:
        tasks = await asyncio.gather(
            _open_meteo(client, latitude, longitude),
            _open_meteo_history(client, latitude, longitude),
            fetch_soil_profile_async(client, latitude, longitude),
            _openlandmap_water(client, latitude, longitude),
            _nasa_history(latitude, longitude, years, polygon),
            return_exceptions=True,
        )
    names = ("open_meteo", "open_meteo_history", "soil_profile", "openlandmap", "nasa")
    fallbacks = {
        "open_meteo": {"status": "unavailable", "current_m3_m3": {key: None for key in MOISTURE_VARIABLES}, "current_percent_vv": {key: None for key in MOISTURE_VARIABLES}, "forecast_daily": []},
        "open_meteo_history": {"status": "unavailable", "daily": []},
        "soil_profile": {"status": "unavailable", "depths": {}, "topsoil_texture_percent": None, "message": "Soil profile provider failed."},
        "openlandmap": {"status": "unavailable", "depths_cm": {}, "message": "OpenLandMap provider failed."},
        "nasa": {"status": "unavailable", "daily": [], "monthly": []},
    }
    return {name: (fallbacks[name] if isinstance(result, BaseException) else result) for name, result in zip(names, tasks)}


async def build_full_soil_report(latitude: float, longitude: float, years: int = 1, polygon: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a 24-hour coordinate-cached soil/climate package with source fallbacks."""
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("coordinates are outside valid latitude/longitude bounds")
    if not 1 <= years <= 5:
        raise ValueError("years must be between 1 and 5")
    # A polygon changes field-level sampling even when its representative pin is the same.
    geometry_key = hashlib.sha256(json.dumps(polygon, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16] if polygon else "point"
    key = (round(latitude, 3), round(longitude, 3), years, geometry_key)
    cached = _REPORT_CACHE.get(key)
    if cached and cached[0] > monotonic():
        return {**cached[1], "cache": {"hit": True, "ttl_seconds": round(cached[0] - monotonic())}}
    lock = _REPORT_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        cached = _REPORT_CACHE.get(key)
        if cached and cached[0] > monotonic():
            return {**cached[1], "cache": {"hit": True, "ttl_seconds": round(cached[0] - monotonic())}}
        datasets = await _collect_external(latitude, longitude, years, polygon)
        soil = datasets["soil_profile"]
        oml = datasets["openlandmap"]
        live = datasets["open_meteo"]
        nasa = datasets["nasa"]
        daily = nasa.get("daily", [])
        last_power = next((record for record in reversed(daily) if record.get("GWETROOT") is not None), None)
        surface_moisture = live.get("current_m3_m3", {}).get(MOISTURE_VARIABLES[0])
        root_moisture = live.get("current_m3_m3", {}).get(MOISTURE_VARIABLES[2])
        if root_moisture is None and last_power:
            # Preserve as a separate normalized wetness index. Do not call it volumetric moisture.
            live["nasa_root_wetness_fraction_fallback"] = last_power.get("GWETROOT")
        surface_fc = _profile_threshold(soil, ("0-5cm",), "field_capacity_m3_m3")
        surface_wp = _profile_threshold(soil, ("0-5cm",), "wilting_point_m3_m3")
        root_fc = _profile_threshold(soil, ("30-60cm", "60-100cm"), "field_capacity_m3_m3")
        root_wp = _profile_threshold(soil, ("30-60cm", "60-100cm"), "wilting_point_m3_m3")
        if oml.get("status") == "available":
            oml_surface_fc = oml.get("depths_cm", {}).get("0", {}).get("field_capacity_pct")
            if oml_surface_fc is not None:
                surface_fc = oml_surface_fc / 100
            oml_surface_wp = oml.get("depths_cm", {}).get("0", {}).get("wilting_point_pct")
            if oml_surface_wp is not None:
                surface_wp = oml_surface_wp / 100
            root_fc_values = [oml.get("depths_cm", {}).get(str(depth), {}).get("field_capacity_pct") for depth in (30, 60, 100)]
            root_wp_values = [oml.get("depths_cm", {}).get(str(depth), {}).get("wilting_point_pct") for depth in (30, 60, 100)]
            if any(value is not None for value in root_fc_values):
                root_fc = sum(value for value in root_fc_values if value is not None) / len([v for v in root_fc_values if v is not None]) / 100
            if any(value is not None for value in root_wp_values):
                root_wp = sum(value for value in root_wp_values if value is not None) / len([v for v in root_wp_values if v is not None]) / 100
        moisture = {
            "status": "available" if surface_moisture is not None or root_moisture is not None else "fallback_only" if last_power else "unavailable",
            "provider": live.get("provider") if live.get("status") == "available" else "NASA POWER wetness fallback" if last_power else None,
            "surface_0_7cm": {"value_m3_m3": surface_moisture, "percent_vv": round(surface_moisture * 100, 1) if surface_moisture is not None else None, "status": _moisture_status(surface_moisture, surface_fc, surface_wp), "depth": "0–7 cm"},
            "root_zone_28_100cm": {"value_m3_m3": root_moisture, "percent_vv": round(root_moisture * 100, 1) if root_moisture is not None else None, "status": _moisture_status(root_moisture, root_fc, root_wp), "depth": "28–100 cm"},
            "other_depths_m3_m3": {key: value for key, value in live.get("current_m3_m3", {}).items() if key not in (MOISTURE_VARIABLES[0], MOISTURE_VARIABLES[2])},
            "nasa_power_root_wetness_fraction": last_power.get("GWETROOT") if last_power else None,
            "nasa_power_surface_wetness_fraction": last_power.get("GWETTOP") if last_power else None,
            "open_meteo_history": datasets["open_meteo_history"], "forecast_daily": live.get("forecast_daily", []),
            "status_thresholds": "Dry/optimal/waterlogged are screening labels using available field-capacity data when present; otherwise broad generic thresholds. Verify with a sensor and crop-specific guidance.",
        }
        profile = {**soil, "openlandmap_water_retention": oml}
        result = {
            "location": {"latitude": latitude, "longitude": longitude, "cache_key": {"latitude": key[0], "longitude": key[1], "boundary": geometry_key}},
            "requested_at": date.today().isoformat(), "years": years,
            "providers": {name: {"status": value.get("status", "unavailable"), "provider": value.get("provider", value.get("source")), "error": value.get("error")} for name, value in datasets.items()},
            "soil_moisture": moisture, "soil_profile": profile,
            "climate": {"status": nasa.get("status", "unavailable"), "provider": nasa.get("source", "NASA POWER"), "monthly": nasa.get("monthly", []), "daily": daily, "source_url": nasa.get("source_url"), "observed_start": nasa.get("observed_start"), "observed_end": nasa.get("observed_end")},
            "cache": {"hit": False, "ttl_seconds": 86400},
        }
        _REPORT_CACHE[key] = (monotonic() + 86400, result)
        return result
