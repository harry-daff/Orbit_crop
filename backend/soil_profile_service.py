"""ISRIC SoilGrids point profile adapter with depth and unit normalization."""

from __future__ import annotations

from time import monotonic
from typing import Any

import httpx
import requests

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
DEPTHS = ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm")
PROPERTIES = ("sand", "silt", "clay", "cfvo", "bdod", "phh2o", "soc", "wv0033", "wv1500")
_CACHE: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}


def _cache_key(latitude: float, longitude: float) -> tuple[float, float]:
    return round(latitude, 3), round(longitude, 3)


def _parse_profile(payload: dict[str, Any], latitude: float, longitude: float) -> dict[str, Any]:
    properties = payload["properties"]
    # SoilGrids v2 serializes the requested layers as a list. Also accept the
    # older dict-shaped structure used by mirrors and cached responses.
    normalized: dict[str, dict[str, dict[str, Any]]] = {}
    layer_list = properties.get("layers")
    if isinstance(layer_list, list):
        for layer in layer_list:
            if not isinstance(layer, dict) or not isinstance(layer.get("name"), str):
                continue
            property_name = layer["name"]
            for depth in layer.get("depths", []):
                if not isinstance(depth, dict) or not isinstance(depth.get("label"), str):
                    continue
                normalized.setdefault(property_name, {})[depth["label"]] = depth.get("values", {})
    else:
        normalized = properties

    layers: dict[str, dict[str, Any]] = {}
    for depth in DEPTHS:
        raw: dict[str, float | None] = {}
        for property_name in PROPERTIES:
            property_depth = normalized.get(property_name, {}).get(depth, {})
            mean = property_depth.get("mean") if isinstance(property_depth, dict) else None
            raw[property_name] = float(mean) if isinstance(mean, (int, float)) and mean >= 0 else None

        sand, silt, clay = (raw.get(key) for key in ("sand", "silt", "clay"))
        texture_percent = None
        texture_class = None
        if all(value is not None for value in (sand, silt, clay)):
            total = sand + silt + clay
            if total > 0:
                texture_percent = {"sand": round(sand / total * 100, 1), "silt": round(silt / total * 100, 1), "clay": round(clay / total * 100, 1)}
                texture_class = usda_texture_class(**texture_percent)

        # SoilGrids scale factors: sand/silt/clay g/kg; cfvo per mil; bdod cg/cm³;
        # phh2o pH*10; soc dg/kg; wv0033/wv1500 in 10^-3 m³/m³.
        rock_pct = raw["cfvo"] / 10 if raw["cfvo"] is not None else None
        bulk_density = raw["bdod"] / 100 if raw["bdod"] is not None else None
        ph = raw["phh2o"] / 10 if raw["phh2o"] is not None else None
        soc_g_kg = raw["soc"] / 10 if raw["soc"] is not None else None
        field_capacity = raw["wv0033"] / 1000 if raw["wv0033"] is not None else None
        wilting_point = raw["wv1500"] / 1000 if raw["wv1500"] is not None else None
        rock_vol_fraction = (rock_pct or 0.0) / 100.0
        porosity = max(0.0, min(0.8, (1.0 - rock_vol_fraction) * (1.0 - bulk_density / 2.65))) if bulk_density is not None else None
        layers[depth] = {
            "texture_percent": texture_percent, "usda_texture_class": texture_class,
            "rock_fragments_percent": round(rock_pct, 1) if rock_pct is not None else None,
            "bulk_density_g_cm3": round(bulk_density, 3) if bulk_density is not None else None,
            "estimated_porosity_fraction": round(porosity, 3) if porosity is not None else None,
            "ph_h2o": round(ph, 1) if ph is not None else None,
            "organic_carbon_g_kg": round(soc_g_kg, 2) if soc_g_kg is not None else None,
            "field_capacity_m3_m3": round(field_capacity, 3) if field_capacity is not None else None,
            "wilting_point_m3_m3": round(wilting_point, 3) if wilting_point is not None else None,
            "plant_available_water_m3_m3": round(max(0, field_capacity - wilting_point), 3) if field_capacity is not None and wilting_point is not None else None,
            "compaction_signal": _compaction_signal(bulk_density),
        }

    top_texture = layers[DEPTHS[0]]["texture_percent"]
    return {
        "status": "available" if any(layer["texture_percent"] or layer["rock_fragments_percent"] is not None or layer["ph_h2o"] is not None for layer in layers.values()) else "partial",
        "provider": "ISRIC SoilGrids 2.0", "source_url": SOILGRIDS_URL,
        "latitude": latitude, "longitude": longitude, "resolution_m": 250,
        "depths": layers, "topsoil_texture_percent": top_texture,
        "wrb_soil_group": {"status": "unavailable", "value": None, "message": "SoilGrids v2 point properties do not return a WRB reference soil group."},
        "bedrock_depth_cm": {"status": "unavailable", "value": None, "message": "No validated bedrock-depth property was returned by the requested SoilGrids v2 profile."},
        "message": "Modeled global soil prediction, not a parcel survey; confirm texture, compaction, and pH with a local soil test.",
    }


def _compaction_signal(bulk_density: float | None) -> str | None:
    if bulk_density is None:
        return None
    # Broad mineral-soil screening thresholds; crop and texture dependent.
    return "possible_restriction" if bulk_density >= 1.6 else "moderate" if bulk_density >= 1.4 else "low_screening_concern"


def usda_texture_class(sand: float, silt: float, clay: float) -> str:
    """Approximate USDA texture class from normalized sand/silt/clay percentages."""
    if silt + 1.5 * clay < 15:
        return "Sand"
    if silt + 2 * clay < 30:
        return "Loamy sand"
    if (clay >= 7 and clay < 20 and sand > 52 and silt + 2 * clay >= 30) or (clay < 7 and silt < 50 and sand > 43):
        return "Sandy loam"
    if clay >= 7 and clay < 27 and silt >= 28 and silt < 50 and sand <= 52:
        return "Loam"
    if silt >= 50 and clay >= 12 and clay < 27:
        return "Silt loam"
    if silt >= 80 and clay < 12:
        return "Silt"
    if clay >= 35 and sand >= 45:
        return "Sandy clay"
    if clay >= 40 and silt >= 40 and sand <= 20:
        return "Silty clay"
    if clay >= 40:
        return "Clay"
    if clay >= 27 and clay < 40 and sand < 20:
        return "Silty clay loam"
    if clay >= 27 and clay < 40 and sand >= 20 and sand < 45:
        return "Clay loam"
    if clay >= 20 and clay < 35 and sand >= 45:
        return "Sandy clay loam"
    if silt >= 50 and clay < 27:
        return "Silt loam"
    return "Loam"


async def fetch_soil_profile_async(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    """Fetch all requested profile properties/depths in one async API request."""
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("coordinates are outside valid latitude/longitude bounds")
    key = _cache_key(latitude, longitude)
    cached = _CACHE.get(key)
    if cached and cached[0] > monotonic():
        return cached[1]
    params: list[tuple[str, str | float]] = [("lon", latitude_to_query(longitude)), ("lat", latitude_to_query(latitude)), ("value", "mean")]
    params.extend(("property", item) for item in PROPERTIES)
    params.extend(("depth", item) for item in DEPTHS)
    try:
        response = await client.get(SOILGRIDS_URL, params=params, timeout=httpx.Timeout(6.0, connect=2.5))
        response.raise_for_status()
        result = _parse_profile(response.json(), latitude, longitude)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        result = _unavailable(latitude, longitude, f"SoilGrids profile is unavailable: {str(exc)[:220]}")
    _CACHE[key] = (monotonic() + (86400 if result["status"] == "available" else 900), result)
    return result


def latitude_to_query(value: float) -> float:
    """Keep upstream coordinates at their submitted precision."""
    return float(value)


def _unavailable(latitude: float, longitude: float, message: str) -> dict[str, Any]:
    return {
        "status": "unavailable", "provider": "ISRIC SoilGrids 2.0", "source_url": SOILGRIDS_URL,
        "latitude": latitude, "longitude": longitude, "resolution_m": 250, "depths": {},
        "topsoil_texture_percent": None,
        "wrb_soil_group": {"status": "unavailable", "value": None, "message": "No WRB class was returned."},
        "bedrock_depth_cm": {"status": "unavailable", "value": None, "message": "No bedrock-depth estimate was returned."},
        "message": message,
    }


def fetch_soil_texture(latitude: float, longitude: float, session: requests.Session | None = None) -> dict[str, Any]:
    """Synchronous compatibility wrapper used by the legacy soil route/tests."""
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("coordinates are outside valid latitude/longitude bounds")
    client = session or requests.Session()
    params = [("lon", longitude), ("lat", latitude), ("depth", "0-5cm"), ("value", "mean")]
    params.extend(("property", name) for name in ("sand", "silt", "clay"))
    try:
        response = client.get(SOILGRIDS_URL, params=params, timeout=(3, 8))
        response.raise_for_status()
        profile = _parse_profile(response.json(), latitude, longitude)
        top = profile["depths"]["0-5cm"]
        return {"status": profile["status"], "provider": profile["provider"], "source_url": profile["source_url"], "latitude": latitude, "longitude": longitude, "depth": "0–5 cm", "raw_unit": "g/kg", "texture_percent": top["texture_percent"], "texture_class": top["usda_texture_class"], "message": profile["message"]}
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        return {"status": "unavailable", "provider": "ISRIC SoilGrids", "source_url": SOILGRIDS_URL, "latitude": latitude, "longitude": longitude, "depth": "0–5 cm", "texture_percent": None, "texture_class": None, "message": f"SoilGrids could not return texture for this coordinate: {str(exc)[:240]}"}
