"""FastAPI application exposing NASA weather, soil status, and crop planning."""

from __future__ import annotations

import os
import math
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from .nasa_service import NasaPowerError, fetch_field_power_data, geodesic_area_hectares, monthly_climatology, soil_health_status
from .rotation_engine import analyze_site, catalog, custom_crop_profile, validate_rotation_sequence
from .country_profiles import COUNTRY_PROFILES
from .soil_profile_service import fetch_soil_texture

app = FastAPI(title="Orbit_crop API", version="2.0.0", description="Field-aware NASA climate history and crop feasibility planning.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()],
    allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["*"],
)


class PlanRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    soil_type: Literal["Loamy", "Clay", "Sandy", "Laterite"]
    previous_crop: str = Field(min_length=1, max_length=40)
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


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "Orbit_crop API", "version": app.version}


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
