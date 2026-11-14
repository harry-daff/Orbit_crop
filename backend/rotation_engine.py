"""Crop matching and transparent rotation rules for Orbit_crop."""

from __future__ import annotations

from typing import Any

SOIL_OPTIONS = {"loamy", "clay", "sandy", "laterite"}
HEAVY_FEEDERS = {"rice", "maize", "wheat", "sugarcane"}

# Advisory ranges are broad screening values, not cultivar-specific prescriptions.
CROPS: dict[str, dict[str, Any]] = {
    "Pulses": {"family": "legume", "water": (1.2, 5.0), "temp": (18, 34), "soils": ["Loamy", "Clay", "Sandy", "Laterite"], "ph": [5.5, 7.5], "season": "Kharif or Rabi", "sow": "June–July or October–November", "harvest": "3–5 months after sowing", "irrigation": "Light irrigation at flowering and pod filling; avoid waterlogging.", "risk": "Low–medium", "market": "Regional demand varies by pulse species", "yield": "0.6–1.8 t/ha, highly species-dependent", "pros": ["Biological nitrogen fixation", "Usually lower water demand than cereals", "Useful break crop"], "cons": ["Yield sensitive to flowering-stage drought", "Storage pests require monitoring"], "actions": ["Test soil pH and correct acidity where advised.", "Choose locally released, disease-resistant seed; use inoculant only when recommended.", "Prepare a fine, well-drained seedbed and sow at locally recommended spacing.", "Apply nutrients from soil-test recommendations; avoid excessive nitrogen.", "Scout weekly for pod borers, aphids, and disease; use integrated pest management.", "Harvest when pods mature and dry grain safely before storage."]},
    "Groundnut": {"family": "legume", "water": (2.0, 6.0), "temp": (20, 32), "soils": ["Loamy", "Sandy", "Laterite"], "ph": [5.8, 7.0], "season": "Kharif or Rabi", "sow": "June–July (rainfed) or January–February", "harvest": "4–5 months after sowing", "irrigation": "Keep moisture steady at pegging and pod formation; ensure drainage.", "risk": "Medium", "market": "Oilseed and food markets; check local buying points", "yield": "1.0–2.5 t/ha pods, variety and management dependent", "pros": ["Legume rotation value", "Multiple food and oil markets"], "cons": ["Waterlogging harms pegging and pods", "Aflatoxin risk if drying/storage are poor"], "actions": ["Select a locally adapted, tested variety and certified seed.", "Prepare loose, friable soil and provide drainage channels.", "Inoculate seed only with locally recommended Rhizobium strains.", "Supply calcium/gypsum around pegging only where soil tests or extension advice support it.", "Monitor leaf spots and soil pests; rotate to reduce disease pressure.", "Lift at maturity and dry pods promptly to safe moisture before storage."]},
    "Soybean": {"family": "legume", "water": (3.0, 7.0), "temp": (20, 32), "soils": ["Loamy", "Clay"], "ph": [6.0, 7.5], "season": "Kharif", "sow": "June–July after dependable monsoon onset", "harvest": "3–4 months after sowing", "irrigation": "Usually rainfed; irrigate during flowering/pod fill if dry.", "risk": "Medium", "market": "Oilseed and feed demand; confirm local procurement", "yield": "1.0–2.5 t/ha, strongly region-dependent", "pros": ["Nitrogen-fixing rotation option", "Oil and meal markets"], "cons": ["Sensitive to waterlogging", "Disease and seed quality risks"], "actions": ["Use locally recommended seed and inoculant if needed.", "Ensure field drainage before monsoon sowing.", "Sow into moist soil at the recommended depth and spacing.", "Use soil-test-based phosphorus, potassium, and sulfur management.", "Scout for defoliators, stem fly, and foliar disease; follow local IPM thresholds.", "Harvest when pods are mature and grain moisture is suitable for storage."]},
    "Rice": {"family": "cereal", "water": (5.0, 12.0), "temp": (22, 35), "soils": ["Loamy", "Clay"], "ph": [5.5, 7.0], "season": "Kharif", "sow": "June–July, aligned with monsoon", "harvest": "4–6 months after sowing", "irrigation": "Manage shallow water where appropriate; drain before harvest.", "risk": "Medium–high", "market": "Strong staple demand; prices and procurement vary", "yield": "2.5–6.0 t/ha paddy, region and system dependent", "pros": ["Staple crop with established markets", "Suitable cultivars available across many ecologies"], "cons": ["High water and nutrient demand in flooded systems", "Blast, sheath blight, and insect risks"], "actions": ["Select a locally recommended duration and water-regime cultivar.", "Level the field and prepare bunds or raised beds to match the production system.", "Use healthy seed; raise nursery only where transplanting is practiced.", "Apply split nutrients using soil tests and local recommendations.", "Use alternate wetting/drying where suitable; monitor water and nutrient stress.", "Scout for weeds, stem borer, and disease; harvest at recommended grain maturity."]},
    "Maize": {"family": "cereal", "water": (2.5, 7.0), "temp": (18, 32), "soils": ["Loamy", "Clay"], "ph": [5.8, 7.0], "season": "Kharif, Rabi, or Zaid", "sow": "At reliable rains or with assured irrigation", "harvest": "3–4 months after sowing", "irrigation": "Prioritize tasseling, silking, and grain fill; avoid standing water.", "risk": "Medium", "market": "Food, feed, and industrial markets; regional demand varies", "yield": "3–8 t/ha grain, system dependent", "pros": ["Flexible planting seasons", "Multiple end markets"], "cons": ["Sensitive to drought at silking", "Fall armyworm and lodging risks"], "actions": ["Select a locally adapted hybrid or open-pollinated variety.", "Prepare a well-drained seedbed and plan weed control before sowing.", "Sow at locally recommended plant density and seed depth.", "Split nitrogen applications based on soil test and crop stage.", "Scout early for fall armyworm and use integrated pest management.", "Harvest at physiological maturity and dry grain promptly."]},
    "Wheat": {"family": "cereal", "water": (1.0, 4.0), "temp": (10, 25), "soils": ["Loamy", "Clay"], "ph": [6.0, 7.5], "season": "Rabi", "sow": "October–December", "harvest": "4–5 months after sowing", "irrigation": "Schedule light irrigations at crown-root initiation and grain fill.", "risk": "Medium", "market": "Staple and procurement markets; policy varies by region", "yield": "2–5 t/ha, climate and input dependent", "pros": ["Established grain markets", "Fits post-monsoon rotations"], "cons": ["Heat at grain fill reduces yield", "Rust and nutrient stress risks"], "actions": ["Choose heat- and disease-appropriate local cultivars.", "Prepare a firm, level seedbed and use timely sowing.", "Use certified seed and recommended seed treatment.", "Base fertilizer and split nitrogen on soil test and local guidance.", "Irrigate critical growth stages and monitor rust and weeds.", "Harvest when grain is mature and dry before storage."]},
    "Millets": {"family": "cereal", "water": (0.8, 4.0), "temp": (20, 35), "soils": ["Loamy", "Sandy", "Laterite"], "ph": [5.0, 7.5], "season": "Kharif", "sow": "June–July after effective rains", "harvest": "3–4 months after sowing", "irrigation": "Often rainfed; lifesaving irrigation during long dry spells.", "risk": "Low–medium", "market": "Growing specialty demand; verify local buyers", "yield": "0.8–2.5 t/ha, species and system dependent", "pros": ["Often suited to lower-rainfall systems", "Crop diversification and nutrition value"], "cons": ["Market access and post-harvest handling can constrain returns", "Species-specific pest risks"], "actions": ["Choose a locally adapted millet species and variety.", "Prepare a weed-free seedbed; retain moisture with suitable soil cover.", "Sow after effective rains at recommended spacing.", "Use soil-test-based nutrients; avoid excess nitrogen on lodging-prone varieties.", "Control weeds early and scout for locally important pests.", "Harvest at grain maturity and dry/store to prevent losses."]},
    "Cotton": {"family": "fiber", "water": (2.0, 6.0), "temp": (21, 35), "soils": ["Loamy", "Clay", "Laterite"], "ph": [5.8, 8.0], "season": "Kharif", "sow": "May–July with warm soil and adequate moisture", "harvest": "5–7 months after sowing", "irrigation": "Avoid water stress during flowering and boll development.", "risk": "High", "market": "Fiber market depends on grade, procurement, and local ginning", "yield": "0.5–2.0 t/ha lint, highly system dependent", "pros": ["Potential cash crop where markets and ginning are accessible", "Multiple harvests"], "cons": ["Long season and high pest-management burden", "Price and weather exposure"], "actions": ["Confirm buyer, seed legality, and local cultivar recommendations.", "Prepare a drained field and establish a uniform stand.", "Use certified seed and locally advised seed treatment.", "Base nutrients on soil testing and crop removal guidance.", "Scout regularly for sucking pests and bollworms; protect beneficial insects.", "Pick clean, dry cotton in stages and store separately by grade."]},
    "Vegetables": {"family": "mixed", "water": (2.0, 7.0), "temp": (15, 32), "soils": ["Loamy", "Sandy", "Laterite"], "ph": [5.5, 7.0], "season": "Year-round by species and local climate", "sow": "Stagger by species and local frost/heat windows", "harvest": "Varies by species; commonly 1–4 months", "irrigation": "Use frequent, measured irrigation; mulch and check drainage.", "risk": "High", "market": "Highly perishable; confirm buyers and cold-chain access", "yield": "Species-specific; cannot estimate for mixed vegetables", "pros": ["Potentially high value per area", "Flexible crop choice"], "cons": ["Price volatility and perishability", "Frequent labor and pest scouting"], "actions": ["Choose one named vegetable and target market before planting.", "Use a soil test and prepare beds suited to drainage and irrigation.", "Select locally adapted seed and raise healthy transplants if required.", "Apply nutrients in split doses according to crop and soil tests.", "Use drip/mulch where practical and scout pests with IPM.", "Harvest at market maturity and plan same-day handling."]},
    "Sunflower": {"family": "oilseed", "water": (1.5, 5.0), "temp": (18, 34), "soils": ["Loamy", "Sandy", "Laterite"], "ph": [6.0, 7.5], "season": "Rabi or short-season windows", "sow": "Use local planting calendar and avoid heat at flowering", "harvest": "3–4 months after sowing", "irrigation": "Protect bud formation and flowering from water stress.", "risk": "Medium", "market": "Oilseed demand; verify local procurement", "yield": "0.8–2.0 t/ha seed, management dependent", "pros": ["Diversifies cereal-heavy rotations", "Moderate season length"], "cons": ["Bird damage and pollination constraints", "Market availability varies"], "actions": ["Confirm a local seed source and market outlet.", "Prepare a well-drained, level seedbed.", "Sow at recommended spacing with viable seed.", "Use soil-test-based nutrients and avoid excess nitrogen.", "Protect pollinators; scout for head pests and diseases.", "Harvest mature heads and dry seed before storage."]},
    "Sorghum": {"family": "cereal", "water": (0.8, 4.5), "temp": (20, 36), "soils": ["Loamy", "Clay", "Sandy", "Laterite"], "ph": [5.5, 8.0], "season": "Kharif or Rabi, region dependent", "sow": "At locally reliable rainfall onset", "harvest": "3–4 months after sowing", "irrigation": "Mostly rainfed; irrigate at booting/flowering during extended drought.", "risk": "Low–medium", "market": "Grain, fodder, and feed markets vary regionally", "yield": "1–4 t/ha grain, system dependent", "pros": ["Drought adaptation in suitable cultivars", "Grain and fodder uses"], "cons": ["Bird damage and grain mold in humid harvests", "Local market access can be limited"], "actions": ["Select a locally tested dual-purpose or grain cultivar.", "Prepare a weed-free seedbed and conserve soil moisture.", "Sow promptly after effective rainfall.", "Apply nutrients based on soil test and intended grain/fodder use.", "Scout for shoot fly, stem borer, and grain mold risk.", "Harvest at maturity and dry panicles/grain promptly."]},
}

BOTANICAL_FAMILIES = {
    "Pulses": "Fabaceae (species dependent)", "Groundnut": "Fabaceae", "Soybean": "Fabaceae",
    "Rice": "Poaceae", "Maize": "Poaceae", "Wheat": "Poaceae", "Millets": "Poaceae (species dependent)",
    "Sorghum": "Poaceae", "Cotton": "Malvaceae", "Vegetables": "Species dependent", "Sunflower": "Asteraceae",
}
for _crop_name, _botanical_family in BOTANICAL_FAMILIES.items():
    CROPS[_crop_name]["botanical_family"] = _botanical_family


def catalog() -> list[dict[str, Any]]:
    """Return all available crop feasibility profiles."""
    return [{"crop": name, **info} for name, info in CROPS.items()]


def analyze_site(monthly: list[dict[str, Any]], soil_type: str, previous_crop: str, country_code: str | None = None, adapt_to_country: bool = False) -> dict[str, Any]:
    """Score all crops, diversify recommendations, and create a three-season plan."""
    soil = soil_type.strip().lower()
    previous = previous_crop.strip().lower()
    if soil not in SOIL_OPTIONS:
        raise ValueError(f"soil_type must be one of: {', '.join(sorted(SOIL_OPTIONS))}")
    if not monthly:
        raise ValueError("monthly NASA climatology is required")
    rains = [float(item["rainfall_mm_day"]) for item in monthly if item.get("rainfall_mm_day") is not None]
    temps = [float(item["temperature_c"]) for item in monthly if item.get("temperature_c") is not None]
    wetness = [float(item["root_zone_wetness"]) for item in monthly if item.get("root_zone_wetness") is not None]
    if not rains or not temps:
        raise ValueError("NASA data is missing rainfall or temperature observations")
    mean_rain = sum(rains) / len(rains)
    mean_temp = sum(temps) / len(temps)
    mean_wet = sum(wetness) / len(wetness) if wetness else None
    wettest = max((m for m in monthly if m.get("rainfall_mm_day") is not None), key=lambda m: m["rainfall_mm_day"])
    driest = min((m for m in monthly if m.get("rainfall_mm_day") is not None), key=lambda m: m["rainfall_mm_day"])
    scored = []
    for name, info in CROPS.items():
        rlo, rhi = info["water"]; tlo, thi = info["temp"]
        rain_fit = max(0.0, 1 - abs(mean_rain - (rlo + rhi) / 2) / max((rhi - rlo) * 1.5, 0.1))
        temp_fit = max(0.0, 1 - abs(mean_temp - (tlo + thi) / 2) / max((thi - tlo) * 1.2, 0.1))
        soil_fit = 1.0 if soil in {value.lower() for value in info["soils"]} else 0.25
        score = 0.45 * rain_fit + 0.35 * temp_fit + 0.20 * soil_fit
        reasons = [f"Climate fit uses {mean_temp:.1f}°C average and {mean_rain:.1f} mm/day historical average"]
        if not soil_fit == 1.0:
            score -= 0.16
            reasons.append("Soil is outside this crop's preferred screening types")
        if previous in HEAVY_FEEDERS and info["family"] == "legume":
            score += 0.25; reasons.append("Rotation bonus: legume after a nitrogen-demanding crop")
        if previous == name.lower():
            score -= 0.32; reasons.append("Reduced to discourage repeating the same crop")
        if previous in {"rice", "maize"} and name in {"Rice", "Maize"}:
            score -= 0.16; reasons.append("Reduced to help break cereal pest/disease cycles")
        if mean_wet is not None and mean_wet > 0.75 and "Clay" not in info["soils"]:
            score -= 0.08; reasons.append("High root-zone wetness raises drainage risk")
        from .country_profiles import get_country_profile
        profile = get_country_profile(country_code) if adapt_to_country else None
        if profile and name.lower() in {crop.lower() for crop in profile["priority_crops"]}:
            score += 0.08
            reasons.append(f"Country staple-priority signal: {profile['country']}")
        risk = "High" if score < 0.35 or name in {"Cotton", "Vegetables"} else "Medium" if score < 0.62 else "Low–medium"
        scored.append((name, max(0.0, min(1.0, score)), reasons, risk))
    scored.sort(key=lambda row: row[1], reverse=True)
    # Ensure top choices do not collapse to one crop family when there are alternatives.
    diverse = []
    for row in scored:
        if all(CROPS[item[0]]["family"] != CROPS[row[0]]["family"] for item in diverse):
            diverse.append(row)
    ordered = diverse + [row for row in scored if row not in diverse]
    if previous in HEAVY_FEEDERS and not any(CROPS[row[0]]["family"] == "legume" for row in ordered[:3]):
        legume = next(row for row in scored if CROPS[row[0]]["family"] == "legume")
        ordered = [legume] + [row for row in ordered if row != legume]
    recommendations = [{"crop": name, "score": round(score * 100), "risk_profile": risk, "reasons": reasons, **CROPS[name]} for name, score, reasons, risk in ordered]
    timeline = []
    seen_families: set[str] = set()
    for season, crop in enumerate(recommendations[:3], 1):
        family = crop["family"]
        note = "Legume phase can contribute biologically fixed nitrogen." if family == "legume" else "Rotate crop families and monitor locally important pests."
        if family in seen_families:
            note = "This family repeats because its climate score ranks well; consider choosing an alternative to reduce pest carryover."
        seen_families.add(family)
        timeline.append({"season": season, "crop": crop["crop"], "sowing_window": crop["sow"], "harvest_window": crop["harvest"], "irrigation_advice": crop["irrigation"], "rotation_note": note})
    wettest_rain = float(wettest["rainfall_mm_day"])
    return {
        "climate_classification": "monsoon-heavy" if wettest_rain >= 6 else "seasonally wet" if wettest_rain >= 3 else "arid / water-limited",
        "water_availability": "high" if mean_rain >= 4.5 and (mean_wet is None or mean_wet >= 0.45) else "moderate" if mean_rain >= 2 else "limited",
        "summary": {"mean_rainfall_mm_day": round(mean_rain, 2), "mean_temperature_c": round(mean_temp, 1), "mean_root_zone_wetness": round(mean_wet, 3) if mean_wet is not None else None, "wettest_month": wettest["month_name"], "driest_month": driest["month_name"]},
        "recommendations": recommendations,
        "country_adjustment": profile if adapt_to_country else None,
        "rotation_timeline": timeline,
        "caveat": "Climate scores are a broad screening aid, not a yield forecast. Validate crop choice, dates, inputs, economics, soil test results, and pest advice with local extension services.",
    }


def custom_crop_profile(name: str, botanical_family: str = "Unknown") -> dict[str, Any]:
    """Create an explicit user-defined crop shell without inventing agronomy values."""
    crop = name.strip()
    if not crop or len(crop) > 80:
        raise ValueError("Crop name must contain 1–80 characters")
    family = botanical_family.strip()[:80] or "Unknown"
    return {
        "crop": crop, "family": "custom", "botanical_family": family,
        "season": "Set local planting window", "sow": "Use locally verified sowing window",
        "harvest": "Set from locally recommended cultivar duration", "irrigation": "Schedule from crop needs, soil moisture, and local extension guidance.",
        "water": None, "temp": None, "soils": [], "ph": None, "yield": "Not estimated for a custom crop",
        "market": "Confirm buyers and market access locally", "risk": "Unknown", "risk_profile": "Unknown",
        "pros": ["Allows a locally selected or experimental crop"],
        "cons": ["Climate fit, yield, inputs, pest profile, and market risks need local validation"],
        "actions": ["Confirm species, cultivar, seed source, and intended market with local extension services.", "Test soil texture, pH, salinity, and nutrients; prepare a seedbed suited to the species and drainage.", "Use verified planting depth, spacing, and sowing dates for the chosen cultivar.", "Set irrigation and nutrient milestones using crop guidance, soil tests, and field observations.", "Identify local weeds, pests, and diseases; scout regularly and use integrated pest management.", "Harvest at cultivar-specific maturity, then dry, grade, and store using crop-specific safe handling guidance."],
        "custom_profile": True, "profile_confidence": "User-defined; no crop-specific reference profile available.",
    }


def validate_rotation_sequence(sequence: list[dict[str, Any]], previous_crop: str | None = None) -> dict[str, Any]:
    """Warn on adjacent botanical-family repeats and nitrogen-depleting sequences."""
    warnings = []
    if sequence and (previous_crop or "").strip().lower() in HEAVY_FEEDERS:
        first = sequence[0]
        family = (first.get("botanical_family") or "").lower()
        if first.get("family") != "legume" and "fabaceae" not in family:
            warnings.append({"season": 1, "type": "nitrogen_break", "message": f"After {previous_crop}, consider a legume or cover crop before another non-legume."})
    for index in range(1, len(sequence)):
        previous, current = sequence[index - 1], sequence[index]
        before_family = (previous.get("botanical_family") or "Unknown").lower()
        family = (current.get("botanical_family") or "Unknown").lower()
        if before_family != "unknown" and family != "unknown" and "species dependent" not in family and before_family == family:
            warnings.append({"season": index + 1, "type": "family_repeat", "message": f"{current['crop']} follows another {current.get('botanical_family')} crop; consider a family break to reduce shared pest and disease pressure."})
        prev_name = previous.get("crop", "").lower()
        current_is_legume = current.get("family") == "legume" or "fabaceae" in family
        if prev_name in HEAVY_FEEDERS and not current_is_legume:
            warnings.append({"season": index + 1, "type": "nitrogen_break", "message": f"After {previous['crop']}, consider a legume or cover crop before another non-legume."})
    return {"valid": not warnings, "warnings": warnings}
