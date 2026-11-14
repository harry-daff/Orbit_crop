"""Transparent, rule-based crop suitability and rotation recommendations.

Recommendations are screening guidance, not a substitute for local extension
advice, soil tests, cultivar choice, or an in-field weather forecast.
"""

from __future__ import annotations

from typing import Any

SOILS = {"loamy", "clay", "sandy", "laterite"}

CROPS: dict[str, dict[str, Any]] = {
    "Pulses": {"water": (1.2, 5.0), "temp": (18, 34), "soils": {"loamy", "clay", "sandy", "laterite"}, "family": "legume", "season": "Kharif or Rabi", "sow": "June–July or October–November", "harvest": "3–5 months after sowing", "irrigation": "Light irrigation at flowering and pod filling; avoid waterlogging."},
    "Groundnut": {"water": (2.0, 6.0), "temp": (20, 32), "soils": {"loamy", "sandy", "laterite"}, "family": "legume", "season": "Kharif or Rabi", "sow": "June–July (rainfed) or January–February", "harvest": "4–5 months after sowing", "irrigation": "Keep moisture steady at pegging and pod formation; ensure drainage."},
    "Soybean": {"water": (3.0, 7.0), "temp": (20, 32), "soils": {"loamy", "clay"}, "family": "legume", "season": "Kharif", "sow": "June–July with dependable monsoon onset", "harvest": "3–4 months after sowing", "irrigation": "Usually rainfed; irrigate during flowering/pod fill if dry."},
    "Rice": {"water": (5.0, 12.0), "temp": (22, 35), "soils": {"loamy", "clay"}, "family": "cereal", "season": "Kharif", "sow": "June–July, aligned with monsoon", "harvest": "4–6 months after sowing", "irrigation": "Maintain shallow water only where suitable; drain before harvest."},
    "Maize": {"water": (2.5, 7.0), "temp": (18, 32), "soils": {"loamy", "clay"}, "family": "cereal", "season": "Kharif, Rabi, or Zaid", "sow": "At reliable rains or with assured irrigation", "harvest": "3–4 months after sowing", "irrigation": "Prioritize tasseling, silking, and grain fill; avoid standing water."},
    "Wheat": {"water": (1.0, 4.0), "temp": (10, 25), "soils": {"loamy", "clay"}, "family": "cereal", "season": "Rabi", "sow": "October–December", "harvest": "4–5 months after sowing", "irrigation": "Schedule light irrigations at crown-root initiation and grain fill."},
    "Millets": {"water": (0.8, 4.0), "temp": (20, 35), "soils": {"loamy", "sandy", "laterite"}, "family": "cereal", "season": "Kharif", "sow": "June–July after effective rains", "harvest": "3–4 months after sowing", "irrigation": "Often rainfed; provide lifesaving irrigation during long dry spells."},
    "Cotton": {"water": (2.0, 6.0), "temp": (21, 35), "soils": {"loamy", "clay", "laterite"}, "family": "fiber", "season": "Kharif", "sow": "May–July with warm soil and adequate moisture", "harvest": "5–7 months after sowing", "irrigation": "Avoid water stress during flowering and boll development."},
    "Vegetables": {"water": (2.0, 7.0), "temp": (15, 32), "soils": {"loamy", "sandy", "laterite"}, "family": "mixed", "season": "Year-round by crop and local climate", "sow": "Stagger by species and local frost/heat windows", "harvest": "Varies by species; commonly 1–4 months", "irrigation": "Use frequent, measured irrigation; mulch and check drainage."},
}

N_FEEDERS = {"rice", "maize", "wheat", "sugarcane"}
LEGUMES = ["Pulses", "Groundnut", "Soybean"]


def analyze_site(monthly: list[dict[str, Any]], soil_type: str, previous_crop: str) -> dict[str, Any]:
    """Score candidate crops using monthly NASA climatology and rotation rules."""
    soil = soil_type.strip().lower()
    previous = previous_crop.strip().lower()
    if soil not in SOILS:
        raise ValueError(f"soil_type must be one of: {', '.join(sorted(SOILS))}")
    if not monthly:
        raise ValueError("monthly NASA climatology is required")

    valid_rain = [float(m["rainfall_mm_day"]) for m in monthly if m.get("rainfall_mm_day") is not None]
    valid_temp = [float(m["temperature_c"]) for m in monthly if m.get("temperature_c") is not None]
    valid_wet = [float(m["root_zone_wetness"]) for m in monthly if m.get("root_zone_wetness") is not None]
    mean_rain = sum(valid_rain) / len(valid_rain) if valid_rain else 0.0
    mean_temp = sum(valid_temp) / len(valid_temp) if valid_temp else 25.0
    mean_wet = sum(valid_wet) / len(valid_wet) if valid_wet else None
    wettest = max(monthly, key=lambda m: m.get("rainfall_mm_day") if m.get("rainfall_mm_day") is not None else -1)
    driest = min(monthly, key=lambda m: m.get("rainfall_mm_day") if m.get("rainfall_mm_day") is not None else float("inf"))
    wettest_rain = wettest.get("rainfall_mm_day") or 0
    climate = "monsoon-heavy" if wettest_rain >= 6 else "seasonally wet" if wettest_rain >= 3 else "arid / water-limited"
    water = "high" if mean_rain >= 4.5 and (mean_wet is None or mean_wet >= 0.45) else "moderate" if mean_rain >= 2 else "limited"

    scored = []
    for crop, info in CROPS.items():
        low_rain, high_rain = info["water"]
        low_temp, high_temp = info["temp"]
        rain_fit = max(0.0, 1 - abs(mean_rain - (low_rain + high_rain) / 2) / ((high_rain - low_rain) * 1.5))
        temp_fit = max(0.0, 1 - abs(mean_temp - (low_temp + high_temp) / 2) / ((high_temp - low_temp) * 1.2))
        soil_fit = 1.0 if soil in info["soils"] else 0.25
        score = 0.45 * rain_fit + 0.35 * temp_fit + 0.20 * soil_fit
        reason = [f"historical temperature and rainfall fit ({mean_temp:.1f}°C mean; {mean_rain:.1f} mm/day annual daily-rate average)"]
        if soil_fit == 1:
            reason.append(f"compatible with {soil} soil")
        if previous in N_FEEDERS and info["family"] == "legume":
            score += 0.32
            reason.append("rotation priority: legume after a nitrogen-demanding crop")
        if previous == crop.lower():
            score -= 0.40
            reason.append("reduced to discourage repeating the same crop")
        if previous in {"rice", "maize"} and crop in {"Rice", "Maize"}:
            score -= 0.20
            reason.append("reduced to help break cereal pest and disease cycles")
        scored.append((crop, max(0.0, min(1.0, score)), reason))

    # If the prior crop is a heavy N feeder, guarantee a legume in the top set.
    scored.sort(key=lambda item: item[1], reverse=True)
    if previous in N_FEEDERS and not any(CROPS[item[0]]["family"] == "legume" for item in scored[:3]):
        best_legume = max((item for item in scored if CROPS[item[0]]["family"] == "legume"), key=lambda item: item[1])
        scored = [best_legume] + [item for item in scored if item[0] != best_legume[0]]

    recommendations = [
        {"crop": crop, "score": round(score * 100), "reasons": reasons, **CROPS[crop]}
        for crop, score, reasons in scored[:3]
    ]
    chosen = recommendations[0]
    timeline = []
    for index, crop in enumerate([chosen, recommendations[1], recommendations[2]], start=1):
        timeline.append({
            "season": index,
            "crop": crop["crop"],
            "sowing_window": crop["sow"],
            "harvest_window": crop["harvest"],
            "irrigation_advice": crop["irrigation"],
            "rotation_note": "Legume phase helps replenish biologically available nitrogen." if crop["family"] == "legume" else "Rotate crop families and monitor local pest pressure.",
        })

    return {
        "climate_classification": climate,
        "water_availability": water,
        "summary": {"mean_rainfall_mm_day": round(mean_rain, 2), "mean_temperature_c": round(mean_temp, 1), "mean_root_zone_wetness": round(mean_wet, 3) if mean_wet is not None else None, "wettest_month": wettest["month_name"], "driest_month": driest["month_name"]},
        "recommendations": recommendations,
        "rotation_timeline": timeline,
        "caveat": "NASA POWER is gridded climate data, not a plot-scale sensor. Validate with local rainfall records, soil tests, crop variety, and extension guidance.",
    }
