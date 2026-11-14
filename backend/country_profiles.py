"""Small, transparent staple-priority hints; this is not a fertilizer law database."""

from __future__ import annotations

COUNTRY_PROFILES = {
    "IN": {"country": "India", "priority_crops": ["Rice", "Wheat", "Pulses", "Millets", "Maize"], "source": "FAOSTAT crop production data", "source_url": "https://www.fao.org/faostat/en/#data/QCL", "note": "Staple-priority ranking hint only. No state-specific input or fertilizer regulation is encoded."},
    "KE": {"country": "Kenya", "priority_crops": ["Maize", "Pulses", "Sorghum", "Millets"], "source": "FAOSTAT crop production data", "source_url": "https://www.fao.org/faostat/en/#data/QCL", "note": "Staple-priority ranking hint only. No county-specific input or fertilizer regulation is encoded."},
    "PH": {"country": "Philippines", "priority_crops": ["Rice", "Maize", "Pulses"], "source": "FAOSTAT crop production data", "source_url": "https://www.fao.org/faostat/en/#data/QCL", "note": "Staple-priority ranking hint only. No province-specific input or fertilizer regulation is encoded."},
    "BR": {"country": "Brazil", "priority_crops": ["Soybean", "Maize", "Sorghum"], "source": "FAOSTAT crop production data", "source_url": "https://www.fao.org/faostat/en/#data/QCL", "note": "Staple-priority ranking hint only. State-specific requirements and current market conditions are not encoded."},
    "US": {"country": "United States", "priority_crops": ["Maize", "Soybean", "Wheat", "Cotton"], "source": "FAOSTAT crop production data", "source_url": "https://www.fao.org/faostat/en/#data/QCL", "note": "Staple-priority ranking hint only. State, county, and program requirements are not encoded."},
}


def get_country_profile(code: str | None) -> dict | None:
    return COUNTRY_PROFILES.get((code or "").upper())
