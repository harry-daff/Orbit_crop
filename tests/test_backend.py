from pydantic import ValidationError

from backend import main
from backend.main import app
from backend.nasa_service import _value_in_kwh, fetch_power_data, geodesic_area_hectares, monthly_climatology
from backend.rotation_engine import analyze_site, catalog, custom_crop_profile, validate_rotation_sequence
from backend.soil_profile_service import fetch_soil_texture


def sample_daily():
    return [
        {"date": "2025-07-01", "PRECTOTCORR": 6.0, "T2M": 27.0, "GWETROOT": 0.62, "GWETTOP": 0.44, "ALLSKY_SFC_SW_DWN": 5.2},
        {"date": "2025-01-01", "PRECTOTCORR": 1.0, "T2M": 19.0, "GWETROOT": 0.38, "GWETTOP": 0.25, "ALLSKY_SFC_SW_DWN": 4.8},
    ]


def test_solar_unit_normalization():
    assert _value_in_kwh(3.6, "MJ/m^2/day") == 1.0
    assert _value_in_kwh(4.25, "kW-hr/m^2/day") == 4.25


def test_nasa_response_parser_converts_solar_and_keeps_wetness():
    from datetime import date, timedelta

    day = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    parameter_data = {
        "PRECTOTCORR": {day: 2.1}, "T2M": {day: 24.5},
        "ALLSKY_SFC_SW_DWN": {day: 36.0}, "GWETROOT": {day: 0.55}, "GWETTOP": {day: 0.31},
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"properties": {"parameter": parameter_data}, "parameters": {"ALLSKY_SFC_SW_DWN": {"units": "MJ/m^2/day"}}}

    class FakeSession:
        def get(self, url, params, timeout):
            assert params["latitude"] == "12.3456789"
            assert params["time-standard"] == "UTC"
            assert params["community"] == "AG"
            return FakeResponse()

    result = fetch_power_data(12.3456789, 75.1234567, 1, session=FakeSession())
    assert result["daily"][0]["ALLSKY_SFC_SW_DWN"] == 10.0
    assert result["daily"][0]["GWETROOT"] == 0.55
    assert result["hydrology_status"] == "available"


def test_monthly_climatology_aggregates_each_calendar_month():
    result = monthly_climatology(sample_daily())
    assert len(result) == 12
    assert result[0]["month_name"] == "Jan"
    assert result[0]["root_zone_wetness"] == 0.38
    assert result[6]["rainfall_mm_day"] == 6.0
    assert result[1]["temperature_c"] is None


def test_geodesic_area_of_small_field_is_positive():
    ring = [[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01], [0, 0]]
    area = geodesic_area_hectares(ring)
    assert 100 < area < 130


def test_rotation_engine_returns_diverse_feasible_crops():
    monthly = monthly_climatology(sample_daily())
    result = analyze_site(monthly, "Loamy", "Rice")
    assert len(result["recommendations"]) == len(catalog())
    assert len(result["rotation_timeline"]) == 3
    assert any(item["family"] == "legume" for item in result["recommendations"][:3])
    assert all(0 <= item["score"] <= 100 for item in result["recommendations"])


def test_plan_endpoint_uses_polygon_and_returns_soil_status(monkeypatch):
    def fake_fetch(lat, lon, years, polygon=None):
        assert polygon is not None
        return {
            "source": "NASA POWER", "source_url": "https://power.larc.nasa.gov/api/temporal/daily/point",
            "requested_start": "2025-01-01", "requested_end": "2025-12-31",
            "observed_start": "2025-01-01", "observed_end": "2025-12-31",
            "time_standard": "UTC", "solar_unit": "kWh/m²/day", "daily": sample_daily(),
                "hydrology_status": "available", "hydrology_error": None,
            "sampling": {"method": "perimeter_multi_point_mean", "coordinates": [[0.0, 0.0]]},
        }

    monkeypatch.setattr(main, "fetch_field_power_data", fake_fetch)
    polygon = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01], [0, 0]]]}}
    from backend.main import PlanRequest

    request = PlanRequest(latitude=0.005, longitude=0.005, soil_type="Loamy", previous_crop="Rice", years=1, field_geojson=polygon)
    result = main.create_plan(request)
    assert result["field"]["area_hectares"] > 100
    assert result["soil_health"]["root_zone_wetness"] == 0.38
    assert result["soil_health"]["texture"]["status"] == "not_configured"


def test_plan_rejects_out_of_bounds_polygon():
    polygon = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[181, 0], [0, 0], [0, 1], [181, 0]]]}}
    from backend.main import PlanRequest

    try:
        PlanRequest(latitude=0, longitude=0, soil_type="Loamy", previous_crop="Rice", field_geojson=polygon)
    except ValidationError:
        return
    raise AssertionError("out-of-bounds field polygon should fail validation")


def test_plan_rejects_malformed_or_zero_area_polygon():
    from backend.main import PlanRequest

    for geojson in (
        {"type": "Feature", "geometry": None},
        {"type": "Polygon", "coordinates": [[[0, 0], [0, 0], [0, 0], [0, 0]]]},
        {"type": "Polygon", "coordinates": [[None, [1, 0], [1, 1], [0, 0]]]},
    ):
        try:
            PlanRequest(latitude=0, longitude=0, soil_type="Loamy", previous_crop="Rice", field_geojson=geojson)
        except (ValidationError, TypeError):
            continue
        raise AssertionError("malformed field geometry should fail validation")


def test_custom_crop_is_free_choice_and_does_not_invent_ranges():
    crop = custom_crop_profile("Amaranth", "Amaranthaceae")
    assert crop["crop"] == "Amaranth"
    assert crop["botanical_family"] == "Amaranthaceae"
    assert crop["temp"] is None and crop["water"] is None and crop["ph"] is None
    assert len(crop["actions"]) == 2
    assert crop["profile_confidence"].startswith("Unrated")


def test_rotation_warns_for_same_family_and_nitrogen_break():
    sequence = [
        {"crop": "Maize", "family": "cereal", "botanical_family": "Poaceae"},
        {"crop": "Wheat", "family": "cereal", "botanical_family": "Poaceae"},
    ]
    result = validate_rotation_sequence(sequence, "Rice")
    assert {warning["type"] for warning in result["warnings"]} == {"family_repeat", "nitrogen_break"}


def test_smap_parser_keeps_volumetric_units_and_separate_series():
    from datetime import date, timedelta

    day = (date.today() - timedelta(days=1)).strftime("%Y%m%d")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"properties": {"parameter": {
                "PRECTOTCORR": {day: 1}, "T2M": {day: 22}, "ALLSKY_SFC_SW_DWN": {day: 4},
                "GWETROOT": {day: 0.4}, "GWETTOP": {day: 0.3}, "RZMC": {day: 0.24}, "SFMC": {day: 0.18},
            }}, "parameters": {}}

    class FakeSession:
        def get(self, url, params, timeout):
            return FakeResponse()

    result = fetch_power_data(10, 20, 1, session=FakeSession())
    assert result["daily"][0]["RZMC"] == 0.24
    assert result["daily"][0]["SFMC"] == 0.18
    assert result["smap_status"] == "available"


def test_soilgrids_normalizes_texture_percentages():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"properties": {name: {"0-5cm": {"mean": value}} for name, value in (("sand", 400), ("silt", 350), ("clay", 250))}}

    class FakeSession:
        def get(self, url, params, timeout):
            return FakeResponse()

    result = fetch_soil_texture(1.123, 2.234, session=FakeSession())
    assert result["texture_percent"] == {"sand": 40.0, "silt": 35.0, "clay": 25.0}


def test_soilgrids_provider_errors_return_unavailable(monkeypatch):
    import requests
    from backend import soil_profile_service

    class FailingSession:
        def get(self, url, params, timeout):
            raise requests.Timeout("provider timeout")

    monkeypatch.setattr(soil_profile_service, "_CACHE", {})
    result = soil_profile_service.fetch_soil_texture(8.123, 9.234, session=FailingSession())
    assert result["status"] == "unavailable"
    assert result["texture_percent"] is None
