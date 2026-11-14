"""Best-effort ISRIC SoilGrids point adapter for modeled topsoil texture."""

from __future__ import annotations

from typing import Any

import requests
from time import monotonic

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
_CACHE: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}


class SoilProfileError(RuntimeError):
    """Raised for an unavailable or malformed SoilGrids response."""


def fetch_soil_texture(latitude: float, longitude: float, session: requests.Session | None = None) -> dict[str, Any]:
    """Query 0–5 cm modeled sand/silt/clay and normalize g/kg into fractions."""
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("coordinates are outside valid latitude/longitude bounds")
    cache_key = (round(latitude, 3), round(longitude, 3))
    cached = _CACHE.get(cache_key)
    if cached and cached[0] > monotonic():
        return cached[1]
    client = session or requests.Session()
    params = [("lon", longitude), ("lat", latitude), ("depth", "0-5cm"), ("value", "mean")]
    params.extend(("property", item) for item in ("sand", "silt", "clay"))
    try:
        response = client.get(SOILGRIDS_URL, params=params, timeout=(3, 8))
        response.raise_for_status()
        payload = response.json()
        properties = payload["properties"]
        texture = {}
        for name in ("sand", "silt", "clay"):
            layer = properties[name]
            depth = layer.get("0-5cm", layer.get("0-5 cm", layer))
            value = depth.get("mean") if isinstance(depth, dict) else None
            if value is None or not isinstance(value, (float, int)) or value < 0:
                raise ValueError(f"SoilGrids returned no valid {name} mean")
            texture[name] = float(value)
        total = sum(texture.values())
        if total <= 0:
            raise ValueError("SoilGrids returned zero texture fractions")
        percent = {name: round(value / total * 100, 1) for name, value in texture.items()}
        result = {
            "status": "available", "provider": "ISRIC SoilGrids", "source_url": SOILGRIDS_URL,
            "latitude": latitude, "longitude": longitude, "depth": "0–5 cm", "raw_unit": "g/kg",
            "texture_percent": percent,
            "message": "Global modeled soil texture estimate. Confirm at field scale with a laboratory sample.",
        }
        _CACHE[cache_key] = (monotonic() + 6 * 60 * 60, result)
        return result
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        result = {
            "status": "unavailable", "provider": "ISRIC SoilGrids", "source_url": SOILGRIDS_URL,
            "latitude": latitude, "longitude": longitude, "depth": "0–5 cm",
            "texture_percent": None, "message": f"SoilGrids could not return texture for this coordinate: {str(exc)[:240]}",
        }
        _CACHE[cache_key] = (monotonic() + 60, result)
        return result
