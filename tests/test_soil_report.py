"""Regression coverage for multi-source soil reporting and suitability scoring."""

import asyncio

from backend import full_soil_report
from backend.crop_suitability import rank_crops
from backend.main import CustomCropRequest, FullSoilReportRequest, create_custom_crop, full_soil_report as report_endpoint
from backend.nasa_service import monthly_climatology
from backend.soil_profile_service import DEPTHS, PROPERTIES, _parse_profile


def test_soilgrids_documented_layers_response_is_parsed_across_depths():
    layers = []
    for name in PROPERTIES:
        depths = []
        for depth in DEPTHS:
            value = {
                "sand": 400, "silt": 350, "clay": 250, "cfvo": 120,
                "bdod": 135, "phh2o": 65, "soc": 180, "wv0033": 300,
                "wv1500": 100,
            }[name]
            depths.append({"label": depth, "values": {"mean": value}})
        layers.append({"name": name, "unit_measure": "mapped unit", "depths": depths})

    result = _parse_profile({"properties": {"layers": layers}}, 10.123456, 20.654321)
    assert result["status"] == "available"
    assert result["depths"]["0-5cm"]["texture_percent"] == {"sand": 40.0, "silt": 35.0, "clay": 25.0}
    assert result["depths"]["100-200cm"]["rock_fragments_percent"] == 12.0
    assert result["depths"]["30-60cm"]["bulk_density_g_cm3"] == 1.35


def _mock_datasets():
    monthly = monthly_climatology([
        {"date": "2025-01-01", "PRECTOTCORR": 2.0, "T2M": 24.0, "GWETROOT": 0.4, "GWETTOP": 0.3, "ALLSKY_SFC_SW_DWN": 4.5},
        {"date": "2025-07-01", "PRECTOTCORR": 5.0, "T2M": 29.0, "GWETROOT": 0.6, "GWETTOP": 0.4, "ALLSKY_SFC_SW_DWN": 5.0},
    ])
    profile = {"status": "unavailable", "depths": {}, "message": "test fixture"}
    return {
        "open_meteo": {
            "status": "available", "provider": "Open-Meteo test", "current_m3_m3": {
                full_soil_report.MOISTURE_VARIABLES[0]: 0.22,
                full_soil_report.MOISTURE_VARIABLES[1]: 0.24,
                full_soil_report.MOISTURE_VARIABLES[2]: 0.28,
                full_soil_report.MOISTURE_VARIABLES[3]: 0.31,
            }, "forecast_daily": [],
        },
        "open_meteo_history": {"status": "available", "daily": []},
        "soil_profile": profile,
        "openlandmap": {"status": "unavailable", "depths_cm": {}, "message": "unavailable"},
        "nasa": {
            "status": "available", "source": "NASA POWER", "source_url": "https://power.larc.nasa.gov/",
            "daily": [{"date": "2025-07-01", "GWETROOT": 0.62, "GWETTOP": 0.31}], "monthly": monthly,
            "observed_start": "2025-01-01", "observed_end": "2025-07-01",
        },
    }


def test_full_report_has_volumetric_units_and_distinct_power_fallback(monkeypatch):
    async def fake_collect(*_args):
        return _mock_datasets()

    monkeypatch.setattr(full_soil_report, "_collect_external", fake_collect)
    monkeypatch.setattr(full_soil_report, "_REPORT_CACHE", {})
    monkeypatch.setattr(full_soil_report, "_REPORT_LOCKS", {})
    result = asyncio.run(full_soil_report.build_full_soil_report(10.0, 20.0, 2))
    assert result["soil_moisture"]["surface_0_7cm"]["percent_vv"] == 22.0
    assert result["soil_moisture"]["root_zone_28_100cm"]["percent_vv"] == 28.0
    assert result["soil_moisture"]["nasa_power_root_wetness_fraction"] == 0.62
    assert result["soil_moisture"]["status"] == "available"


def test_power_wetness_fallback_is_not_mislabeled_as_volumetric(monkeypatch):
    async def fake_collect(*_args):
        data = _mock_datasets()
        data["open_meteo"] = {"status": "unavailable", "current_m3_m3": {name: None for name in full_soil_report.MOISTURE_VARIABLES}, "forecast_daily": []}
        return data

    monkeypatch.setattr(full_soil_report, "_collect_external", fake_collect)
    monkeypatch.setattr(full_soil_report, "_REPORT_CACHE", {})
    monkeypatch.setattr(full_soil_report, "_REPORT_LOCKS", {})
    result = asyncio.run(full_soil_report.build_full_soil_report(11.0, 21.0, 1))
    assert result["soil_moisture"]["status"] == "fallback_only"
    assert result["soil_moisture"]["root_zone_28_100cm"]["value_m3_m3"] is None
    assert result["soil_moisture"]["nasa_power_root_wetness_fraction"] == 0.62


def test_openlandmap_wms_parser_reads_layer_id_and_gray_index():
    from backend.full_soil_report import _openlandmap_water

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"features": [
                {"id": "predicted250m:sol_watercontent.33kPa_usda.4b1c_m_250m_b30..30cm_1950..2017_v0.1.1", "properties": {"GRAY_INDEX": 31}},
                {"id": "predicted250m:sol_watercontent.1500kPa_usda.4b1c_m_250m_b30..30cm_1950..2017_v0.1.1", "properties": {"GRAY_INDEX": 9}},
            ]}

    class FakeClient:
        async def get(self, _url, params, timeout):
            assert "33kPa" in params["layers"]
            assert "1500kPa" in params["layers"]
            return FakeResponse()

    result = asyncio.run(_openlandmap_water(FakeClient(), 1, 2))
    assert result["status"] == "available"
    assert result["depths_cm"]["30"]["field_capacity_pct"] == 31
    assert result["depths_cm"]["30"]["wilting_point_pct"] == 9


def test_full_report_cache_does_not_mix_different_boundaries(monkeypatch):
    calls = []

    async def fake_collect(*args):
        calls.append(args)
        return _mock_datasets()

    monkeypatch.setattr(full_soil_report, "_collect_external", fake_collect)
    monkeypatch.setattr(full_soil_report, "_REPORT_CACHE", {})
    monkeypatch.setattr(full_soil_report, "_REPORT_LOCKS", {})

    async def exercise():
        first = await full_soil_report.build_full_soil_report(10.0001, 20.0001, 1)
        cached = await full_soil_report.build_full_soil_report(10.0002, 20.0002, 1)
        polygon = {"type": "Polygon", "coordinates": [[[20, 10], [20.01, 10], [20.01, 10.01], [20, 10.01], [20, 10]]]}
        separate = await full_soil_report.build_full_soil_report(10.0001, 20.0001, 1, polygon)
        return first, cached, separate

    first, cached, separate = asyncio.run(exercise())
    assert cached["cache"]["hit"] is True
    assert separate["cache"]["hit"] is False
    assert len(calls) == 2


def test_crop_engine_groups_catalog_and_scores_custom_crop():
    result = rank_crops({"monthly": []}, {"depths": {}}, {}, "Rice", "Amaranth", "vegetable")
    assert result["recommendations"]
    assert result["groups"]["vegetable"]
    assert result["groups"]["fruit"]
    assert result["custom_crop_check"]["crop"] == "Amaranth"
    assert result["custom_crop_check"]["probability_pct"] is None
    assert result["custom_crop_check"]["confidence"] == "insufficient data"
    assert result["custom_crop_check"]["profile_source"].startswith("FAO EcoCrop")


def test_ecocrop_ginger_has_species_specific_requirements_and_score():
    monthly = [{"month": month, "rainfall_mm_day": 5.0, "temperature_c": 25.0} for month in range(1, 13)]
    result = rank_crops({"monthly": monthly}, {"depths": {}}, {}, "Maize", "ginger")
    crop = result["custom_crop_check"]
    assert crop["probability_pct"] is not None
    assert crop["temp"] == [19.0, 29.0]
    assert crop["ph"] == [6.0, 7.0]
    assert crop["annual_rainfall_mm"] == [1400.0, 3000.0]
    assert crop["profile_source"].startswith("FAO EcoCrop")
    assert any("mm/year" in item for item in crop["reasons"])


def test_custom_crop_endpoint_looks_up_ginger_instead_of_returning_generic_shell():
    crop = create_custom_crop(CustomCropRequest(name="ginger"))
    assert crop["temp"] == [19.0, 29.0]
    assert crop["ph"] == [6.0, 7.0]
    assert crop["annual_rainfall_mm"] == [1400.0, 3000.0]
    assert crop["profile_source"].startswith("FAO EcoCrop")
    assert crop["yield"].startswith("Not provided")


def test_country_priority_toggle_affects_crop_rank_scores_only_when_enabled():
    baseline = rank_crops({"monthly": []}, {"depths": {}}, {}, "Other")
    adapted = rank_crops({"monthly": []}, {"depths": {}}, {}, "Other", country_code="IN", adapt_to_country=True)
    baseline_rice = next(crop for crop in baseline["recommendations"] if crop["crop"] == "Rice")
    adapted_rice = next(crop for crop in adapted["recommendations"] if crop["crop"] == "Rice")
    assert adapted_rice["score"] == min(100, baseline_rice["score"] + 8)
    assert adapted["country_adjustment"]["country"] == "India"
    assert baseline["country_adjustment"] is None


def test_manual_soil_selection_is_used_when_soilgrid_profile_is_unavailable():
    result = rank_crops({"monthly": []}, {"depths": {}}, {}, "Other", soil_type_hint="Sandy")
    rice = next(crop for crop in result["recommendations"] if crop["crop"] == "Rice")
    assert "User-selected soil type used: Sandy" in rice["reasons"]
    assert rice["data_coverage_pct"] > 0


def test_full_report_endpoint_keeps_legacy_dashboard_data_shape(monkeypatch):
    data = _mock_datasets()
    soil = data["soil_profile"]
    moisture = {
        "status": "available", "surface_0_7cm": {"value_m3_m3": 0.2, "percent_vv": 20.0, "status": "optimal"},
        "root_zone_28_100cm": {"value_m3_m3": 0.25, "percent_vv": 25.0, "status": "optimal"},
        "nasa_power_root_wetness_fraction": 0.5, "nasa_power_surface_wetness_fraction": 0.3,
    }
    async def fake_report(*_args):
        climate = data["nasa"]
        return {"climate": {"monthly": climate["monthly"], "daily": climate["daily"], "source_url": climate["source_url"], "observed_start": climate["observed_start"], "observed_end": climate["observed_end"]}, "soil_profile": soil, "soil_moisture": moisture, "field": {}}

    monkeypatch.setattr("backend.main.build_full_soil_report", fake_report)
    request = FullSoilReportRequest(latitude=10, longitude=20, previous_crop="Rice", years=1)
    result = asyncio.run(report_endpoint(request))
    assert len(result["monthly"]) == 12
    assert result["daily"]
    assert result["field"]["sampling"]["method"] == "NASA POWER point grid"
    assert result["data_source"]["url"] == "https://power.larc.nasa.gov/"


def test_full_report_endpoint_exposes_resolved_soil_class_for_ui(monkeypatch):
    data = _mock_datasets()
    data["soil_profile"] = {
        "status": "available", "provider": "ISRIC SoilGrids 2.0", "message": "modeled",
        "depths": {"0-5cm": {"usda_texture_class": "Sandy loam", "texture_percent": {"sand": 60, "silt": 25, "clay": 15}}},
    }

    async def fake_report(*_args):
        return {
            "climate": {"monthly": data["nasa"]["monthly"], "daily": data["nasa"]["daily"], "provider": "NASA POWER", "source_url": "https://power.larc.nasa.gov/"},
            "soil_profile": data["soil_profile"], "soil_moisture": {"status": "available"},
        }

    monkeypatch.setattr("backend.main.build_full_soil_report", fake_report)
    request = FullSoilReportRequest(latitude=10, longitude=20, previous_crop="Rice", years=1)
    result = asyncio.run(report_endpoint(request))
    assert result["soil_detection"] == {
        "status": "detected", "soil_type": "Sandy loam", "texture_class": "Sandy loam",
        "source": "ISRIC SoilGrids 2.0", "message": "SoilGrids topsoil texture resolved as Sandy loam.",
    }
    assert result["selected_soil_type"] == "Sandy"


def test_geocode_skips_malformed_coordinates_and_returns_labeled_place(monkeypatch):
    from backend import main

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"features": [
                {"geometry": {"coordinates": [77.2, 28.6]}, "properties": {"name": "Delhi", "state": "Delhi", "country": "India", "countrycode": "IN"}},
                {"geometry": {"coordinates": ["bad", 5]}, "properties": {"name": "Malformed"}},
            ]}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(main.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(main, "_GEOCODE_CACHE", {})
    result = asyncio.run(main.geocode("Delhi"))
    assert len(result["results"]) == 1
    assert result["results"][0]["label"] == "Delhi, Delhi, India"
    assert result["results"][0]["country_code"] == "IN"


def test_full_report_http_route_degrades_gracefully_if_every_provider_is_down(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import main

    async def unavailable_report(*_args):
        return {
            "climate": {"status": "unavailable", "monthly": [], "daily": [], "provider": "NASA POWER"},
            "soil_profile": {"status": "unavailable", "depths": {}, "message": "Providers unavailable"},
            "soil_moisture": {"status": "unavailable", "surface_0_7cm": {}, "root_zone_28_100cm": {}},
            "field": {},
        }

    monkeypatch.setattr(main, "build_full_soil_report", unavailable_report)
    with TestClient(main.app) as client:
        response = client.post("/api/full-soil-report", json={"latitude": 10, "longitude": 20, "years": 1})
    assert response.status_code == 200
    data = response.json()
    assert data["monthly"] == []
    assert data["soil_moisture"]["status"] == "unavailable"
    assert data["analysis"]["climate_classification"] == "Climate data unavailable"
    assert data["crop_suitability"]["recommendations"]


def test_full_report_accepts_long_previous_crop_with_boundary():
    polygon = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01], [0, 0]]]}}
    long_crop = "Traditional High-Altitude Aromatic Basmati Rice"  # 47 chars
    req = FullSoilReportRequest(latitude=10, longitude=20, previous_crop=long_crop, years=1, field_geojson=polygon)
    assert req.previous_crop == long_crop


def test_sugarcane_rotation_warns_on_poaceae_repeat():
    from backend.rotation_engine import validate_rotation_sequence
    sequence = [{"crop": "Rice", "family": "cereal", "botanical_family": "Poaceae"}]
    result = validate_rotation_sequence(sequence, previous_crop="Sugarcane")
    types = {warning["type"] for warning in result["warnings"]}
    assert "nitrogen_break" in types
    assert "family_repeat" in types
