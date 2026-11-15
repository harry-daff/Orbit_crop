"""Coverage for the global hazard screening and API contract."""

from fastapi.testclient import TestClient

from backend import main
from backend.disaster_service import _severity_for_weather


def test_hazard_engine_combines_rain_slope_saturation_heat_and_wind():
    weather = {
        "daily": [
            {"date": "2026-11-15", "precipitation_sum": 70, "temperature_2m_max": 42, "temperature_2m_min": 24, "wind_gusts_10m_max": 82, "et0_fao_evapotranspiration": 6, "surface_moisture": 0.44, "root_moisture": 0.39},
            {"date": "2026-11-16", "precipitation_sum": 75, "temperature_2m_max": 40, "temperature_2m_min": 23, "wind_gusts_10m_max": 60, "et0_fao_evapotranspiration": 5, "surface_moisture": 0.42, "root_moisture": 0.38},
            {"date": "2026-11-17", "precipitation_sum": 20, "temperature_2m_max": 39, "temperature_2m_min": 22, "wind_gusts_10m_max": 45, "et0_fao_evapotranspiration": 5, "surface_moisture": 0.40, "root_moisture": 0.37},
        ]
    }
    soil = {"depths": {"0-5cm": {"field_capacity_m3_m3": 0.32}}}
    terrain = {"estimated_slope_degrees": 20}
    flood = {"daily": []}
    conditions, alerts = _severity_for_weather(weather["daily"], soil, terrain, flood, {"temp": (18, 30)})
    risks = conditions["daily"][0]["risks"]
    assert risks["Rain"] == "Warning"
    assert risks["Landslide"] == "Critical"
    assert risks["Heatwave"] == "Critical"
    assert risks["Severe storm"] == "Warning"
    assert {alert["hazard"] for alert in alerts} >= {"Heavy rain", "Heatwave", "Severe storm", "Landslide", "Waterlogging"}


def test_heatwave_and_drought_require_three_consecutive_days():
    daily = [
        {"date": f"2026-11-{15+i}", "precipitation_sum": 0, "temperature_2m_max": 41, "temperature_2m_min": 20, "wind_gusts_10m_max": 10, "et0_fao_evapotranspiration": 5, "surface_moisture": 0.1, "root_moisture": 0.1}
        for i in range(3)
    ]
    soil = {"depths": {"0-5cm": {}}}
    terrain = {"estimated_slope_degrees": 0}
    conditions2, _ = _severity_for_weather(daily[:2], soil, terrain, {"daily": []}, None)
    assert conditions2["daily"][0]["risks"]["Heatwave"] == "Watch"
    assert conditions2["daily"][0]["risks"]["Drought"] == "Safe"
    conditions3, _ = _severity_for_weather(daily, soil, terrain, {"daily": []}, None)
    assert conditions3["daily"][0]["risks"]["Heatwave"] == "Warning"
    assert conditions3["daily"][0]["risks"]["Drought"] == "Warning"


def test_disaster_alert_endpoint_validates_and_passes_location(monkeypatch):
    async def fake_alerts(lat, lon, crop_name=None, country_code=None):
        return {"location": {"latitude": lat, "longitude": lon}, "crop": crop_name, "country": country_code, "active_count": 0}

    monkeypatch.setattr(main, "get_disaster_alerts", fake_alerts)
    client = TestClient(main.app)
    response = client.get("/api/disaster-alerts?lat=12.3&lon=45.6&crop=Maize&country=IN")
    assert response.status_code == 200
    assert response.json()["location"] == {"latitude": 12.3, "longitude": 45.6}
    assert response.json()["crop"] == "Maize"
    assert client.get("/api/disaster-alerts?lat=99&lon=0").status_code == 422
