"""All-crop climate/soil screening with transparent, non-calibrated scores."""

from __future__ import annotations

from typing import Any

from .country_profiles import COUNTRY_PROFILES
from .rotation_engine import CROPS, HEAVY_FEEDERS, custom_crop_profile
from .ecocrop_service import lookup_ecocrop

SCORE_LABEL = "heuristic suitability score (not a statistically calibrated success probability)"


def _range_fit(value: float | None, limits: tuple[float, float] | list[float] | None) -> float | None:
    if value is None or not limits or len(limits) < 2:
        return None
    low, high = float(limits[0]), float(limits[1])
    width = max(high - low, 0.1)
    return max(0.0, 1.0 - abs(value - (low + high) / 2) / (width * 1.5))


def _soil_family(texture_class: str | None, soil_type_hint: str | None = None) -> str | None:
    if not texture_class:
        hint = (soil_type_hint or "").strip().lower()
        return hint if hint in {"loamy", "clay", "sandy", "laterite"} else None
    value = texture_class.lower()
    if "sand" in value and "clay" not in value:
        return "sandy"
    if "clay" in value and "loam" not in value:
        return "clay"
    return "loamy"


def _rotation_advice(name: str, crop: dict[str, Any], previous_crop: str) -> list[str]:
    advice = []
    previous = previous_crop.strip().lower()
    if previous in HEAVY_FEEDERS and crop.get("family") != "legume":
        advice.append(f"Rotation warning: after {previous_crop}, consider a legume or cover crop before another non-legume.")
    previous_info = next((info for crop_name, info in CROPS.items() if crop_name.lower() == previous), None)
    previous_family = previous_info.get("botanical_family") if previous_info else ("Poaceae" if previous == "sugarcane" else None)
    current_family = crop.get("botanical_family")
    if previous_family and current_family and previous_family == current_family:
        advice.append(f"Family-break warning: {name} shares {current_family} with the previous crop; rotate families where practical.")
    if not advice:
        advice.append("Maintain crop-family diversity and use a soil-test-based nutrient plan.")
    return advice


def _score_one(name: str, crop: dict[str, Any], climate: dict[str, Any], profile: dict[str, Any], moisture: dict[str, Any], previous_crop: str, priority_crops: set[str] | None = None, soil_type_hint: str | None = None) -> dict[str, Any]:
    monthly = climate.get("monthly", [])
    rain = [row.get("rainfall_mm_day") for row in monthly if row.get("rainfall_mm_day") is not None]
    temp = [row.get("temperature_c") for row in monthly if row.get("temperature_c") is not None]
    mean_rain = sum(rain) / len(rain) if rain else None
    mean_temp = sum(temp) / len(temp) if temp else None
    soil_layers = profile.get("depths", {})
    top = soil_layers.get("0-5cm", {})
    texture = top.get("usda_texture_class")
    soil_type = _soil_family(texture, soil_type_hint)
    ph = top.get("ph_h2o")
    rock_depth = "30-60cm" if int(crop.get("root_depth_cm", 60)) <= 60 else "60-100cm" if int(crop.get("root_depth_cm", 60)) <= 100 else "100-200cm"
    rock_pct = soil_layers.get(rock_depth, {}).get("rock_fragments_percent")
    root_moisture = moisture.get("root_zone_28_100cm", {}).get("value_m3_m3")

    criteria: list[tuple[str, float, float]] = []
    annual_rain = None
    if monthly:
        # POWER monthly normals are daily rates. Convert each to a monthly total
        # before comparing with EcoCrop's explicitly annual rainfall ranges.
        import calendar
        annual_rain = sum(
            float(row["rainfall_mm_day"]) * calendar.monthrange(2000, int(row.get("month", 1)))[1]
            for row in monthly if row.get("rainfall_mm_day") is not None
        )
    annual_limits = crop.get("annual_rainfall_mm") or crop.get("absolute_annual_rainfall_mm")
    rain_fit = _range_fit(annual_rain, annual_limits) if annual_limits else _range_fit(mean_rain, crop.get("water"))
    temp_fit = _range_fit(mean_temp, crop.get("temp"))
    if rain_fit is not None: criteria.append(("climate_water", rain_fit, 0.25))
    if temp_fit is not None: criteria.append(("temperature", temp_fit, 0.22))
    if soil_type is not None:
        matches = [item.lower() for item in crop.get("soils", [])]
        if matches:
            fit = 1.0 if soil_type in matches or ("loamy" in matches and soil_type == "loamy") else 0.35
            criteria.append(("texture", fit, 0.15))
    if ph is not None:
        ph_limits = crop.get("ph")
        if ph_limits and len(ph_limits) >= 2:
            lo, hi = ph_limits
            fit = 1.0 if lo <= ph <= hi else max(0.0, 1 - min(abs(ph - lo), abs(ph - hi)) / 1.5)
            criteria.append(("ph", fit, 0.12))
    if root_moisture is not None:
        fit = _range_fit(root_moisture, crop.get("moisture_range", [0.12, 0.36]))
        if fit is not None: criteria.append(("root_zone_moisture", fit, 0.12))
    if rock_pct is not None:
        tolerance = float(crop.get("rock_tolerance_pct", 12))
        fit = 1.0 if rock_pct <= tolerance else max(0.0, 1 - (rock_pct - tolerance) / 35)
        criteria.append(("rock_content", fit, 0.08))
    if criteria:
        total_weight = sum(weight for _, _, weight in criteria)
        score = sum(fit * weight for _, fit, weight in criteria) / total_weight
    else:
        score = 0.5
    reasons = []
    if name.casefold() in (priority_crops or set()):
        score = min(1.0, score + 0.08)
        reasons.append("Country staple-priority signal applied; verify local market and policy conditions.")
    if mean_temp is not None: reasons.append(f"Mean air temperature used: {mean_temp:.1f} °C")
    if annual_limits and annual_rain is not None:
        reasons.append(f"Estimated annual precipitation: {annual_rain:.0f} mm/year compared with source annual range {annual_limits[0]:.0f}–{annual_limits[1]:.0f} mm/year")
    elif mean_rain is not None: reasons.append(f"Mean precipitation used: {mean_rain:.2f} mm/day")
    if texture: reasons.append(f"SoilGrids texture: {texture}")
    elif soil_type_hint: reasons.append(f"User-selected soil type used: {soil_type_hint}")
    if ph is not None: reasons.append(f"SoilGrids topsoil pH: {ph:.1f}")
    if rock_pct is not None: reasons.append(f"Coarse fragments at {rock_depth}: {rock_pct:.1f}%")
    warnings = _rotation_advice(name, crop, previous_crop)
    if rock_pct is not None and rock_pct > float(crop.get("rock_tolerance_pct", 12)):
        warnings.append(f"Root-zone rock content may limit establishment at approximately {crop.get('root_depth_cm')} cm rooting depth.")
    coverage = sum(weight for _, _, weight in criteria) / (0.25 + 0.22 + 0.15 + 0.12 + 0.12 + 0.08)
    percentage = round(max(0, min(100, score * 100)))
    return {
        "crop": name, "category": crop.get("category", "field_crop"), "family": crop.get("family"),
        "botanical_family": crop.get("botanical_family"), "score": percentage,
        "probability_pct": percentage, "score_type": SCORE_LABEL,
        "confidence": "moderate" if coverage >= 0.75 else "low" if coverage < 0.45 else "limited",
        "data_coverage_pct": round(coverage * 100), "risk_profile": "High" if percentage < 40 else "Medium" if percentage < 65 else "Low–medium",
        "reasons": reasons, "rotation_advice": warnings, "root_depth_cm": crop.get("root_depth_cm"),
        **crop,
    }


def rank_crops(climate: dict[str, Any], soil_profile: dict[str, Any], moisture: dict[str, Any], previous_crop: str, custom_name: str | None = None, custom_category: str = "field_crop", country_code: str | None = None, adapt_to_country: bool = False, soil_type_hint: str | None = None) -> dict[str, Any]:
    """Score the full library across field crops, vegetables, fruits and custom choice."""
    country_profile = COUNTRY_PROFILES.get((country_code or "").upper()) if adapt_to_country else None
    priorities = {name.casefold() for name in country_profile["priority_crops"]} if country_profile else set()
    candidates = [(name, info) for name, info in CROPS.items()]
    ranked = [_score_one(name, info, climate, soil_profile, moisture, previous_crop, priorities, soil_type_hint) for name, info in candidates]
    ranked.sort(key=lambda item: item["score"], reverse=True)
    custom_result = None
    if custom_name and custom_name.strip():
        match = next((crop for crop in ranked if crop["crop"].casefold() == custom_name.strip().casefold()), None)
        if match:
            custom_result = {**match, "custom_match": True}
        else:
            profile = lookup_ecocrop(custom_name.strip())
            if profile:
                profile.setdefault("root_depth_cm", 100)
                profile.setdefault("rock_tolerance_pct", 12)
                result = _score_one(custom_name.strip(), profile, climate, soil_profile, moisture, previous_crop, priorities, soil_type_hint)
                result.update({key: value for key, value in profile.items() if key not in {"crop", "risk_profile"}})
                result["crop"] = custom_name.strip()
                result.update({"custom_match": False, "score_type": f"{SCORE_LABEL}; ecological requirements from {profile['profile_source']}", "confidence": "limited"})
                if result["data_coverage_pct"] == 0:
                    result.update({"score": None, "probability_pct": None, "confidence": "insufficient data", "risk_profile": "Unrated"})
                result["rotation_advice"] = _rotation_advice(custom_name.strip(), profile, previous_crop)
                custom_result = result
            else:
                unknown = custom_crop_profile(custom_name, "Unknown")
                custom_result = {**unknown, "category": custom_category, "score": None, "probability_pct": None,
                    "data_coverage_pct": 0, "confidence": "not rated", "risk_profile": "Unrated",
                    "score_type": "No matching crop profile in the local catalog or EcoCrop; no score estimated.",
                    "rotation_advice": _rotation_advice(custom_name.strip(), unknown, previous_crop)}
    groups = {category: [crop for crop in ranked if crop["category"] == category] for category in ("field_crop", "vegetable", "fruit")}
    return {"recommendations": ranked, "groups": groups, "custom_crop_check": custom_result, "country_adjustment": country_profile, "score_type": SCORE_LABEL, "caveat": "Percentages are rule-based suitability scores, not calibrated probabilities of yield or financial success."}
