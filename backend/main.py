"""FastAPI application exposing NASA weather, soil status, and crop planning."""

from __future__ import annotations

import os
import math
from time import monotonic
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from .nasa_service import NasaPowerError, fetch_field_power_data, geodesic_area_hectares, monthly_climatology, soil_health_status
from .rotation_engine import CROPS, analyze_site, catalog, custom_crop_profile, validate_rotation_sequence
from .ecocrop_service import lookup_ecocrop
from .country_profiles import COUNTRY_PROFILES
from .soil_profile_service import fetch_soil_texture
from .full_soil_report import build_full_soil_report
from .crop_suitability import rank_crops
from .disaster_service import get_disaster_alerts
from .provenance import SI_PROVENANCE

import httpx

app = FastAPI(title="Orbit_crop API", version="2.0.0", description="Field-aware crop planning. Code and derived planning outputs are SI-assisted; fetched provider data retain their original attribution. See /api/metadata.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()],
    allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["*"],
)

_GEOCODE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


class PlanRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    soil_type: Literal["Loamy", "Clay", "Sandy", "Laterite"]
    previous_crop: str = Field(min_length=1, max_length=80)
    years: int = Field(default=3, ge=1, le=5)
    field_geojson: dict[str, Any] | None = None
    adapt_to_country: bool = False
    country_code: str | None = Field(default=None, min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_polygon(self) -> "PlanRequest":
        if self.field_geojson is None:
            return self
        geometry = self.field_geojson.get("geometry", self.field_geojson)
        if not isinstance(geometry, dict):
            raise ValueError("field_geojson must contain a GeoJSON Polygon geometry object")
        if geometry.get("type") != "Polygon":
            raise ValueError("field_geojson must contain a GeoJSON Polygon")
        rings = geometry.get("coordinates")
        if not isinstance(rings, list) or len(rings) != 1 or not isinstance(rings[0], list) or len(rings[0]) < 4 or len(rings[0]) > 101:
            raise ValueError("field boundary requires 3–100 vertices in a single outer ring")
        ring = rings[0]
        if ring[0] != ring[-1]:
            raise ValueError("GeoJSON polygon ring must be closed (first and last coordinates match)")
        for point in ring:
            if not isinstance(point, list) or len(point) < 2 or not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in point[:2]):
                raise ValueError("Each GeoJSON vertex must be [longitude, latitude]")
            lon, lat = point[:2]
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("Polygon coordinate is outside valid longitude/latitude bounds")
        if geodesic_area_hectares(ring) <= 0:
            raise ValueError("Field boundary area must be greater than zero")
        return self


class FullSoilReportRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    soil_type: Literal["Loamy", "Clay", "Sandy", "Laterite"] | None = None
    previous_crop: str = Field(default="Other", min_length=1, max_length=80)
    years: int = Field(default=1, ge=1, le=5)
    field_geojson: dict[str, Any] | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    adapt_to_country: bool = False
    custom_crop_name: str | None = Field(default=None, max_length=80)
    custom_crop_category: Literal["field_crop", "vegetable", "fruit"] = "field_crop"


@app.post("/api/full-soil-report")
async def full_soil_report(request: FullSoilReportRequest) -> dict[str, Any]:
    """Aggregate cached Open-Meteo, NASA POWER, SoilGrids, and OpenLandMap products."""
    geometry = None
    if request.field_geojson is not None:
        try:
            parsed = PlanRequest(latitude=request.latitude, longitude=request.longitude, soil_type=request.soil_type or "Loamy", previous_crop=request.previous_crop, years=request.years, field_geojson=request.field_geojson)
            geometry = parsed.field_geojson.get("geometry", parsed.field_geojson)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid farm boundary: {exc}") from exc
    try:
        report = await build_full_soil_report(request.latitude, request.longitude, request.years, geometry)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    climate = report["climate"]
    monthly = climate.get("monthly", [])
    soil = report["soil_profile"]
    detected = soil.get("depths", {}).get("0-5cm", {}).get("usda_texture_class")
    detected_type = "Sandy" if detected and "sand" in detected.lower() and "clay" not in detected.lower() else "Clay" if detected and "clay" in detected.lower() and "loam" not in detected.lower() else "Loamy" if detected else None
    selected_soil = detected_type or request.soil_type
    planning_soil = selected_soil or "Loamy"  # Only the legacy climate-plan builder requires a soil category.
    try:
        analysis = analyze_site(monthly, planning_soil, request.previous_crop, request.country_code, request.adapt_to_country) if monthly else {"rotation_timeline": [], "summary": {}, "climate_classification": "Climate data unavailable", "water_availability": "unknown", "caveat": "NASA POWER history is unavailable; score confidence is reduced."}
    except (ValueError, KeyError, TypeError):
        analysis = {"rotation_timeline": [], "summary": {}, "climate_classification": "Climate data incomplete", "water_availability": "unknown", "caveat": "NASA POWER history is incomplete; validate all recommendations locally."}

    crop_scores = rank_crops(climate, soil, report["soil_moisture"], request.previous_crop, request.custom_crop_name, request.custom_crop_category, request.country_code, request.adapt_to_country, selected_soil)
    analysis["recommendations"] = crop_scores["recommendations"]
    analysis["custom_crop_check"] = crop_scores["custom_crop_check"]
    analysis["score_type"] = crop_scores["score_type"]
    report["analysis"] = analysis
    report["content_provenance"] = SI_PROVENANCE
    # Keep the response shape consumed by the existing dashboard views.
    report["monthly"] = monthly
    report["daily"] = climate.get("daily", [])
    report["crop_suitability"] = crop_scores
    report["selected_soil_type"] = selected_soil
    report["soil_detection"] = {
        "status": "detected" if detected else "manual" if request.soil_type else "unavailable",
        "soil_type": detected or request.soil_type,
        "texture_class": detected,
        "source": soil.get("provider") if detected else "Farmer selection" if request.soil_type else None,
        "message": f"SoilGrids topsoil texture resolved as {detected}." if detected else f"Using farmer-selected {request.soil_type} soil type." if request.soil_type else soil.get("message", "Soil type could not be auto-detected; choose a soil type or retry when the soil provider is available."),
    }
    report["previous_crop"] = request.previous_crop
    report["field"] = {
        "geojson": request.field_geojson,
        "area_hectares": geodesic_area_hectares(geometry["coordinates"][0]) if geometry else None,
        "sampling": {"method": "NASA POWER point grid" if not geometry else "NASA POWER polygon vertex sampling"},
    }
    last_power_record = next((record for record in reversed(climate.get("daily", [])) if record.get("GWETROOT") is not None), None)
    report["soil_health"] = {
        "root_zone_wetness": last_power_record.get("GWETROOT") if last_power_record else (climate.get("daily") or [{}])[-1].get("GWETROOT"),
        "surface_wetness": last_power_record.get("GWETTOP") if last_power_record else (climate.get("daily") or [{}])[-1].get("GWETTOP"),
        "smap": {"status": "unavailable", "message": "NASA POWER SMAP alias is supplemental; Open-Meteo provides the current volumetric profile."},
        "texture": soil,
    }
    top_layer = soil.get("depths", {}).get("0-5cm", {})
    texture_class = (top_layer.get("usda_texture_class") or "").lower()
    drainage = "rapid drainage tendency" if "sand" in texture_class and "clay" not in texture_class else "slow drainage tendency" if "clay" in texture_class else "moderate drainage tendency" if texture_class else None
    report["hydrology"] = {
        "water_table": {"status": "unavailable", "depth_m": None, "message": "No parcel-scale groundwater-depth observation is supplied by the connected global soil and weather sources."},
        "drainage": {"class": drainage, "method": "texture_screening_only" if drainage else None, "message": "Broad texture tendency, not an FAO drainage class or measured drainage rate." if drainage else "Needs a soil profile or field infiltration test."},
    }
    report["data_source"] = {
        "name": climate.get("provider", "NASA POWER"), "url": climate.get("source_url"),
        "start": climate.get("observed_start"), "end": climate.get("observed_end"),
        "daily_records": len(climate.get("daily", [])), "time_standard": "UTC",
        "solar_unit": climate.get("solar_unit", "kWh/m²/day"),
        "hydrology_status": report["soil_moisture"].get("status", "unavailable"),
    }
    return report


@app.get("/api/geocode")
async def geocode(q: str = Query(min_length=2, max_length=120)) -> dict[str, Any]:
    """Small cached Photon autocomplete proxy; avoids public Nominatim autocomplete."""
    query = " ".join(q.split())
    key = query.casefold()
    cached = _GEOCODE_CACHE.get(key)
    if cached and cached[0] > monotonic():
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(4.5, connect=2.0), headers={"User-Agent": "Orbit_crop/1.0 (global farm location search)"}) as client:
            response = await client.get("https://photon.komoot.io/api/", params={"q": query, "limit": 6, "lang": "en"})
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("features", []), list):
            raise ValueError("The place-search provider returned an invalid result list.")
        results = []
        for feature in payload.get("features", []):
            if not isinstance(feature, dict):
                continue
            coordinates = feature.get("geometry", {}).get("coordinates", [])
            properties = feature.get("properties", {})
            if not isinstance(coordinates, list) or len(coordinates) < 2 or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in coordinates[:2]):
                continue
            if not isinstance(properties, dict):
                properties = {}
            label = ", ".join(str(properties[field]) for field in ("name", "district", "city", "state", "country") if properties.get(field)) or "Unnamed place"
            results.append({"label": label, "longitude": coordinates[0], "latitude": coordinates[1], "country_code": properties.get("countrycode")})
        result = {"results": results, "provider": "Photon / OpenStreetMap"}
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        result = {"results": [], "provider": "Photon / OpenStreetMap", "error": f"Place search is temporarily unavailable: {str(exc)[:180]}"}
    cache_ttl = 15 if "error" in result else 3600
    _GEOCODE_CACHE[key] = (monotonic() + cache_ttl, result)
    return result


@app.get("/api/disaster-alerts")
async def disaster_alerts(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    crop: str | None = Query(default=None, max_length=80),
    country: str | None = Query(default=None, min_length=2, max_length=2),
) -> dict[str, Any]:
    """Return a cached global hazard outlook and source-issued nearby alerts."""
    try:
        report = await get_disaster_alerts(lat, lon, crop, country)
        report["content_provenance"] = SI_PROVENANCE
        return report
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "Orbit_crop API", "version": app.version}


@app.get("/api/metadata")
def metadata() -> dict[str, Any]:
    """Return SI-generation disclosure and distinguish it from external source data."""
    return {"service": "Orbit_crop", "content_provenance": SI_PROVENANCE}


@app.get("/api/crops")
def get_crops() -> dict[str, list[dict[str, Any]]]:
    """Return the full crop feasibility catalog used by the recommendation engine."""
    return {"crops": catalog()}


@app.get("/api/countries")
def get_countries() -> dict[str, Any]:
    return {"countries": [{"code": code, **profile} for code, profile in COUNTRY_PROFILES.items()]}


class CustomCropRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    botanical_family: str = Field(default="Unknown", max_length=80)


@app.post("/api/crops/custom")
def create_custom_crop(request: CustomCropRequest) -> dict[str, Any]:
    try:
        known = next((name for name in CROPS if name.casefold() == request.name.strip().casefold()), None)
        if known:
            return {"crop": known, **CROPS[known], "custom_match": True, "profile_source": "Orbit_crop curated crop catalog"}
        profile = lookup_ecocrop(request.name)
        if profile:
            return profile
        return custom_crop_profile(request.name, request.botanical_family)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class RotationRequest(BaseModel):
    sequence: list[dict[str, Any]] = Field(min_length=1, max_length=12)
    previous_crop: str | None = Field(default=None, max_length=80)


@app.post("/api/rotation/validate")
def check_rotation(request: RotationRequest) -> dict[str, Any]:
    return validate_rotation_sequence(request.sequence, request.previous_crop)


@app.post("/api/plan")
def create_plan(request: PlanRequest) -> dict[str, Any]:
    """Fetch NASA history for a precise point or multi-point field boundary."""
    try:
        geometry = request.field_geojson.get("geometry", request.field_geojson) if request.field_geojson else None
        nasa = fetch_field_power_data(request.latitude, request.longitude, request.years, geometry)
        monthly = monthly_climatology(nasa["daily"])
        analysis = analyze_site(monthly, request.soil_type, request.previous_crop, request.country_code, request.adapt_to_country)
        health = soil_health_status(request.latitude, request.longitude, monthly, nasa["daily"])
        area = geodesic_area_hectares(geometry["coordinates"][0]) if geometry else None
    except (NasaPowerError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=502 if isinstance(exc, NasaPowerError) else 422, detail=str(exc)) from exc
    return {
        "location": {"latitude": request.latitude, "longitude": request.longitude},
        "field": {"geojson": request.field_geojson, "area_hectares": round(area, 3) if area is not None else None, "sampling": nasa["sampling"]},
        "soil_type": request.soil_type, "previous_crop": request.previous_crop,
        "data_source": {"name": nasa["source"], "url": nasa["source_url"], "start": nasa["observed_start"], "end": nasa["observed_end"], "requested_start": nasa["requested_start"], "requested_end": nasa["requested_end"], "daily_records": len(nasa["daily"]), "time_standard": nasa["time_standard"], "solar_unit": nasa["solar_unit"], "hydrology_status": nasa["hydrology_status"], "hydrology_error": nasa.get("hydrology_error"), "smap_status": nasa.get("smap_status", "unavailable"), "smap_error": nasa.get("smap_error")},
        "monthly": monthly, "daily": nasa["daily"], "analysis": analysis, "soil_health": health,
    }


@app.post("/api/soil")
def soil_status(request: PlanRequest) -> dict[str, Any]:
    """Retrieve available NASA POWER wetness history (texture/NDVI stay explicit)."""
    try:
        geometry = request.field_geojson.get("geometry", request.field_geojson) if request.field_geojson else None
        nasa = fetch_field_power_data(request.latitude, request.longitude, request.years, geometry)
        monthly = monthly_climatology(nasa["daily"])
    except (NasaPowerError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=502 if isinstance(exc, NasaPowerError) else 422, detail=str(exc)) from exc
    return soil_health_status(request.latitude, request.longitude, monthly, nasa["daily"])


@app.post("/api/soil/profile")
def soil_profile(request: PlanRequest) -> dict[str, Any]:
    """Best-effort point texture query; failures return explicit unavailable status."""
    try:
        return fetch_soil_texture(request.latitude, request.longitude)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# In production, serve the built PWA and API from one origin. In local Vite
# development this directory is absent, so FastAPI remains API-only.
_FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.isdir(_FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
