"""NASA POWER daily agroclimatology data client and monthly summarizer."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import requests

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = ("PRECTOTCORR", "T2M", "GWETROOT", "ALLSKY_SFC_SW_DWN")
PARAMETER_LABELS = {
    "PRECTOTCORR": "Precipitation (mm/day)",
    "T2M": "Temperature at 2 m (°C)",
    "GWETROOT": "Root zone soil wetness (fraction)",
    "ALLSKY_SFC_SW_DWN": "All-sky surface shortwave (kWh/m²/day)",
}


class NasaPowerError(RuntimeError):
    """Raised when NASA POWER data cannot be fetched or parsed."""


def fetch_power_data(
    latitude: float,
    longitude: float,
    years: int = 3,
    *,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Fetch up to five complete years of daily NASA POWER agroclimate data."""
    if not 1 <= years <= 5:
        raise ValueError("years must be between 1 and 5")
    # NASA POWER daily products are often delayed; use the last completed day.
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=365 * years - 1)
    params = {
        "parameters": ",".join(PARAMETERS),
        "community": "AG",
        "longitude": longitude,
        "latitude": latitude,
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }
    client = session or requests.Session()
    try:
        response = client.get(POWER_URL, params=params, timeout=(8, 90))
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise NasaPowerError(f"NASA POWER request failed: {exc}") from exc

    try:
        raw = payload["properties"]["parameter"]
        daily: list[dict[str, Any]] = []
        # POWER uses -999 for unavailable values. Ignore incomplete days.
        for day_key in sorted(raw[PARAMETERS[0]]):
            values = {key: raw[key].get(day_key) for key in PARAMETERS}
            if any(value is None or value == -999 for value in values.values()):
                continue
            daily.append({"date": f"{day_key[:4]}-{day_key[4:6]}-{day_key[6:]}", **values})
        if not daily:
            raise ValueError("NASA returned no complete daily records")
    except (KeyError, TypeError, ValueError) as exc:
        raise NasaPowerError(f"Unexpected NASA POWER response: {exc}") from exc

    return {
        "source": "NASA POWER",
        "source_url": POWER_URL,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "latitude": latitude,
        "longitude": longitude,
        "daily": daily,
        "metadata": payload.get("properties", {}).get("parameter", {}),
    }


def monthly_climatology(daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return calendar-month averages across all daily records supplied."""
    buckets: dict[int, dict[str, list[float]]] = {
        month: {key: [] for key in PARAMETERS} for month in range(1, 13)
    }
    for record in daily:
        month = int(record["date"][5:7])
        for key in PARAMETERS:
            buckets[month][key].append(float(record[key]))

    result = []
    for month in range(1, 13):
        values = buckets[month]
        # Rainfall is reported as a daily rate by POWER; monthly average daily
        # rate makes wet/dry season comparisons consistent across month lengths.
        result.append({
            "month": month,
            "month_name": date(2000, month, 1).strftime("%b"),
            "rainfall_mm_day": round(sum(values["PRECTOTCORR"]) / len(values["PRECTOTCORR"]), 2) if values["PRECTOTCORR"] else None,
            "temperature_c": round(sum(values["T2M"]) / len(values["T2M"]), 2) if values["T2M"] else None,
            "root_zone_wetness": round(sum(values["GWETROOT"]) / len(values["GWETROOT"]), 3) if values["GWETROOT"] else None,
            "solar_kwh_m2_day": round(sum(values["ALLSKY_SFC_SW_DWN"]) / len(values["ALLSKY_SFC_SW_DWN"]), 2) if values["ALLSKY_SFC_SW_DWN"] else None,
        })
    return result


def fetch_deeper_soil_metrics(latitude: float, longitude: float) -> dict[str, Any]:
    """Extension point for future SMAP/OpenLandMap integration.

    SMAP and OpenLandMap products have different spatial/temporal resolution
    and access patterns. No values are fabricated until a provider is wired in.
    """
    return {
        "status": "not_configured",
        "provider": None,
        "latitude": latitude,
        "longitude": longitude,
        "message": "Connect a NASA SMAP or OpenLandMap product here for deeper soil metrics.",
    }
