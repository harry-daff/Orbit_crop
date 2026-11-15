"""Offline crop-name lookup for the FAO EcoCrop requirements snapshot."""

from __future__ import annotations

import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

ECOCROP_FILE = Path(__file__).parent / "data" / "ecocrop.csv"
ECOCROP_SOURCE = "FAO EcoCrop (OpenCLIM snapshot, pinned 2022)"


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


@lru_cache(maxsize=1)
def _read_rows() -> tuple[dict[str, str], ...]:
    # The pinned public snapshot contains a small number of legacy encoded
    # characters despite otherwise being UTF-8. Replacement is safe for the
    # numeric requirements and keeps common/scientific names readable.
    with ECOCROP_FILE.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        return tuple(dict(row) for row in csv.DictReader(handle))


def _number(row: dict[str, str], field: str) -> float | None:
    try:
        value = float(row.get(field, ""))
    except (TypeError, ValueError):
        return None
    return value if value == value and abs(value) != float("inf") and value > -900 else None


def _range(row: dict[str, str], low_key: str, high_key: str) -> list[float] | None:
    low, high = _number(row, low_key), _number(row, high_key)
    return [low, high] if low is not None and high is not None and low < high else None


def _names(row: dict[str, str]) -> list[str]:
    names = [row.get("ScientificName", ""), row.get("COMNAME", ""), row.get("SYNO", "")]
    return [part.strip().strip("'") for value in names if value for part in value.split(",") if part.strip()]


def _soil_classes(value: str) -> list[str]:
    text = (value or "").casefold()
    choices: list[str] = []
    if "heavy" in text:
        choices.extend(("Clay", "Loamy"))
    if "medium" in text:
        choices.append("Loamy")
    if "light" in text:
        choices.append("Sandy")
    if "wide" in text:
        choices.extend(("Loamy", "Clay", "Sandy", "Laterite"))
    return list(dict.fromkeys(choices))


def _category(row: dict[str, str]) -> str:
    category = (row.get("CAT") or "").casefold()
    if "vegetable" in category:
        return "vegetable"
    if any(term in category for term in ("fruit", "plantation", "tree crop")):
        return "fruit"
    return "field_crop"


def lookup_ecocrop(name: str) -> dict[str, Any] | None:
    """Find an exact common/scientific/synonym match and normalize EcoCrop fields.

    EcoCrop ecological ranges are broad expert estimates. They are not yield
    forecasts or cultivar-level production instructions.
    """
    wanted = _normalize(name.strip())
    if not wanted:
        return None
    row = next((candidate for candidate in _read_rows() if any(_normalize(alias) == wanted for alias in _names(candidate))), None)
    if row is None:
        return None

    family_path = row.get("FAMNAME", "")
    family = family_path.split(":")[-1].strip() if family_path else "Unknown"
    botanical = row.get("ScientificName", "") or name.strip()
    temperature = _range(row, "TOPMN", "TOPMX")
    temperature_basis = "optimal" if temperature else "absolute"
    temperature = temperature or _range(row, "TMIN", "TMAX")
    ph = _range(row, "PHOPMN", "PHOPMX")
    ph_basis = "optimal" if ph else "absolute"
    ph = ph or _range(row, "PHMIN", "PHMAX")
    annual_rain = _range(row, "ROPMN", "ROPMX")
    absolute_annual_rain = _range(row, "RMIN", "RMAX")
    days_min, days_max = _number(row, "GMIN"), _number(row, "GMAX")
    days = f"{int(days_min)}–{int(days_max)} days" if days_min is not None and days_max is not None else "not provided"
    depth = (row.get("DEP") or "").casefold()
    root_depth_cm = 35 if "shallow" in depth else 100 if "medium" in depth else 180 if "deep" in depth else None
    soil_preferences = _soil_classes(row.get("TEXT", ""))
    if "wide" in (row.get("TEXT") or "").casefold():
        soil_preferences = ["Loamy", "Clay", "Sandy", "Laterite"]

    optimal_rain_text = f"{int(annual_rain[0])}–{int(annual_rain[1])} mm/year" if annual_rain else "not provided"
    optimal_temp_text = f"{temperature[0]:g}–{temperature[1]:g} °C" if temperature else "not provided"
    optimal_ph_text = f"pH {ph[0]:g}–{ph[1]:g}" if ph else "not provided"
    soil_text = ", ".join(soil_preferences) if soil_preferences else (row.get("TEXT") or "not provided")
    drainage = (row.get("DRA") or "").strip()
    fertility = (row.get("FER") or "").strip()
    category = _category(row)

    actions = [
        f"Confirm the species as {botanical} and select a locally recommended cultivar before ordering seed or planting material.",
        f"Prepare a field with EcoCrop's listed soil texture preference ({soil_text}) and soil depth preference ({row.get('DEP') or 'not specified'}); verify drainage locally.",
        f"Use locally verified planting date, spacing, and planting depth; EcoCrop does not provide cultivar-specific seeding instructions for {name.strip()}.",
        f"Compare local temperature with the EcoCrop {temperature_basis} range ({optimal_temp_text}) and plan water supply against its annual rainfall reference ({optimal_rain_text}).",
        f"Set nutrient inputs from a soil test; the EcoCrop fertility preference is {fertility or 'not specified'} and is not a fertilizer rate.",
        f"Scout for locally important weeds, pests, and diseases; the source describes drainage preference as {drainage or 'not provided'} but does not provide a pesticide schedule.",
        f"Use the locally established maturity and post-harvest guidance; EcoCrop lists a crop-cycle range of {days} and does not provide a verified yield estimate.",
    ]
    return {
        "crop": name.strip(), "scientific_name": botanical, "botanical_family": family,
        "family": family, "category": category, "season": "Use local planting calendar",
        "sow": "Planting window not provided by EcoCrop; confirm with local extension guidance",
        "harvest": f"EcoCrop crop cycle: {days}", "irrigation": f"Use measured soil moisture and local crop water guidance; annual reference rainfall: {optimal_rain_text}.",
        "water": None, "annual_rainfall_mm": annual_rain, "absolute_annual_rainfall_mm": absolute_annual_rain,
        "rainfall_basis": "FAO EcoCrop annual total; not a crop-cycle water requirement",
        "temp": temperature, "temp_basis": temperature_basis, "soils": soil_preferences,
        "soil_texture_source_labels": row.get("TEXT"), "soil_depth_preference": row.get("DEP"),
        "ph": ph, "ph_basis": ph_basis, "yield": "Not provided by EcoCrop; do not infer from ecological suitability.",
        "market": "Market demand and prices are not provided by EcoCrop; check local buyers.",
        "risk": "Ecological screening only", "risk_profile": "Validate locally",
        "pros": [f"Species requirements are available from {ECOCROP_SOURCE}.", f"The listed optimal soil drainage preference is {drainage or 'not provided'} and fertility preference is {fertility or 'not provided'}"],
        "cons": ["EcoCrop gives broad expert-estimated ecological ranges, not guaranteed performance.", "No crop-specific yield, market price, seed spacing, fertilizer rate, or pest-control prescription is included."],
        "actions": actions, "custom_profile": False, "profile_source": ECOCROP_SOURCE,
        "profile_source_url": f"https://ecocrop.apps.fao.org/ecocrop/srv/en/dataSheet?id={row.get('EcoPortCode', '')}",
        "profile_confidence": "Broad species-level ecological reference; cultivar and regional validation needed.",
        "crop_cycle_days": [days_min, days_max] if days_min is not None and days_max is not None else None,
    }
