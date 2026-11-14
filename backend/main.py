"""FastAPI application for the Orbit_crop farmer dashboard."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .nasa_service import NasaPowerError, fetch_deeper_soil_metrics, fetch_power_data, monthly_climatology
from .rotation_engine import analyze_site

app = FastAPI(title="Orbit_crop API", version="1.0.0", description="NASA POWER based crop planning and rotation screening.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class PlanRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    soil_type: Literal["Loamy", "Clay", "Sandy", "Laterite"]
    previous_crop: str = Field(min_length=1, max_length=40)
    years: int = Field(default=3, ge=1, le=5)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "Orbit_crop API"}


@app.post("/api/plan")
def create_plan(request: PlanRequest) -> dict:
    """Fetch NASA history and return chart series, scores, and a three-season plan."""
    try:
        nasa = fetch_power_data(request.latitude, request.longitude, request.years)
        monthly = monthly_climatology(nasa["daily"])
        analysis = analyze_site(monthly, request.soil_type, request.previous_crop)
    except (NasaPowerError, ValueError) as exc:
        raise HTTPException(status_code=502 if isinstance(exc, NasaPowerError) else 422, detail=str(exc)) from exc
    with ThreadPoolExecutor(max_workers=1) as pool:
        deeper_soil = pool.submit(fetch_deeper_soil_metrics, request.latitude, request.longitude).result()
    return {"location": {"latitude": request.latitude, "longitude": request.longitude}, "soil_type": request.soil_type, "previous_crop": request.previous_crop, "data_source": {"name": nasa["source"], "url": nasa["source_url"], "start": nasa["requested_start"], "end": nasa["requested_end"], "daily_records": len(nasa["daily"])}, "monthly": monthly, "analysis": analysis, "deeper_soil": deeper_soil}
