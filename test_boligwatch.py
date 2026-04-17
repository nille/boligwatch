"""Tests for SearchConfig, _build_search_config, and to_api_body."""

from __future__ import annotations

import pytest

from boligwatch import SearchConfig, _build_search_config, _RESTRICTIVE_FILTERS


# -- Fixtures ----------------------------------------------------------------

@pytest.fixture
def base_config() -> SearchConfig:
    """Simulates a typical config file with restrictive filters set."""
    return SearchConfig.from_dict({
        "categories": ["rental_apartment", "rental_house"],
        "city_level_1": None,
        "min_lat": 55.63,
        "min_lng": 12.48,
        "max_lat": 55.73,
        "max_lng": 12.80,
        "rooms_min": 3,
        "max_rent": 17000,
        "min_rental_period": 12,
        "order": "DEFAULT",
        "max_pages": 10,
    })


# -- _build_search_config: filter inheritance --------------------------------

class TestBuildSearchConfigInheritance:

    def test_structural_settings_inherited(self, base_config: SearchConfig) -> None:
        result = _build_search_config(base_config)
        assert result.categories == ["rental_apartment", "rental_house"]
        assert result.min_lat == 55.63
        assert result.max_lat == 55.73
        assert result.order == "DEFAULT"
        assert result.max_pages == 10

    def test_restrictive_filters_not_inherited(self, base_config: SearchConfig) -> None:
        result = _build_search_config(base_config)
        assert result.max_rent is None
        assert result.rooms_min is None
        assert result.min_rental_period is None

    def test_all_restrictive_filters_stripped(self, base_config: SearchConfig) -> None:
        rich_config = SearchConfig.from_dict({
            "rooms_min": 2, "rooms_max": 5, "max_rent": 20000,
            "min_size_m2": 60, "min_rental_period": 12,
            "max_available_from": "2026-08-01",
            "pet_friendly": True, "balcony": True, "furnished": True,
            "parking": True, "elevator": True, "shareable": True,
            "student_only": True, "senior_friendly": True,
            "social_housing": True, "newbuild": True,
            "electric_charging_station": True, "dishwasher": True,
            "washing_machine": True, "dryer": True,
        })
        result = _build_search_config(rich_config)
        for field_name in _RESTRICTIVE_FILTERS:
            assert getattr(result, field_name) is None, f"{field_name} should be None"

    def test_explicit_filter_overrides_applied(self, base_config: SearchConfig) -> None:
        result = _build_search_config(
            base_config,
            rooms_min=2, max_rent=15000, min_size_m2=80,
        )
        assert result.rooms_min == 2
        assert result.max_rent == 15000
        assert result.min_size_m2 == 80

    def test_explicit_filter_with_others_still_none(self, base_config: SearchConfig) -> None:
        result = _build_search_config(base_config, min_size_m2=200)
        assert result.min_size_m2 == 200
        assert result.max_rent is None
        assert result.rooms_min is None

    def test_cities_override(self, base_config: SearchConfig) -> None:
        result = _build_search_config(base_config, cities=["frederiksberg"])
        assert result.city_level_1 == ["frederiksberg"]

    def test_cities_lowercased(self, base_config: SearchConfig) -> None:
        result = _build_search_config(base_config, cities=["København", "FREDERIKSBERG"])
        assert result.city_level_1 == ["københavn", "frederiksberg"]

    def test_bbox_override_clears_city(self) -> None:
        city_config = SearchConfig.from_dict({"city_level_1": ["københavn"]})
        result = _build_search_config(
            city_config,
            min_lat=55.6, min_lng=12.4, max_lat=55.7, max_lng=12.6,
        )
        assert result.min_lat == 55.6
        assert result.city_level_1 is None

    def test_bbox_requires_all_four(self, base_config: SearchConfig) -> None:
        with pytest.raises(ValueError, match="All four bbox"):
            _build_search_config(base_config, min_lat=55.6)

    def test_max_pages_override(self, base_config: SearchConfig) -> None:
        result = _build_search_config(base_config, max_pages=20)
        assert result.max_pages == 20

    def test_boolean_filters_pass_through(self, base_config: SearchConfig) -> None:
        result = _build_search_config(
            base_config,
            pet_friendly=True, dishwasher=True, electric_charging_station=True,
        )
        assert result.pet_friendly is True
        assert result.dishwasher is True
        assert result.electric_charging_station is True

    def test_max_available_from_pass_through(self, base_config: SearchConfig) -> None:
        result = _build_search_config(base_config, max_available_from="2026-09-01")
        assert result.max_available_from == "2026-09-01"


# -- to_api_body mapping ----------------------------------------------------

class TestToApiBody:

    def test_minimal_config_has_categories_and_order(self) -> None:
        config = SearchConfig.from_dict({})
        body = config.to_api_body()
        assert body["categories"] == {"values": ["rental_apartment", "rental_house", "rental_townhouse"]}
        assert body["order"] == "DEFAULT"

    def test_city_included(self) -> None:
        config = SearchConfig.from_dict({"city_level_1": ["københavn"]})
        body = config.to_api_body()
        assert body["city_level_1"] == {"values": ["københavn"]}

    def test_rooms_min_only(self) -> None:
        config = SearchConfig.from_dict({"rooms_min": 3})
        body = config.to_api_body()
        assert body["rooms"] == {"gte": 3}

    def test_rooms_max_only(self) -> None:
        config = SearchConfig.from_dict({"rooms_max": 5})
        body = config.to_api_body()
        assert body["rooms"] == {"lte": 5}

    def test_rooms_range(self) -> None:
        config = SearchConfig.from_dict({"rooms_min": 2, "rooms_max": 4})
        body = config.to_api_body()
        assert body["rooms"] == {"gte": 2, "lte": 4}

    def test_max_rent_key(self) -> None:
        config = SearchConfig.from_dict({"max_rent": 15000})
        body = config.to_api_body()
        assert body["max_monthly_rent"] == 15000
        assert "max_rent" not in body

    def test_size_and_rental_period(self) -> None:
        config = SearchConfig.from_dict({"min_size_m2": 80, "min_rental_period": 12})
        body = config.to_api_body()
        assert body["min_size_m2"] == 80
        assert body["min_rental_period"] == 12

    def test_max_available_from(self) -> None:
        config = SearchConfig.from_dict({"max_available_from": "2026-08-01"})
        body = config.to_api_body()
        assert body["max_available_from"] == "2026-08-01"

    def test_bbox_coordinates(self) -> None:
        config = SearchConfig.from_dict({
            "min_lat": 55.6, "min_lng": 12.4, "max_lat": 55.7, "max_lng": 12.6,
        })
        body = config.to_api_body()
        assert body["min_lat"] == 55.6
        assert body["max_lng"] == 12.6

    def test_boolean_filters_included_when_set(self) -> None:
        all_bools = {
            "pet_friendly": True, "balcony": True, "furnished": True,
            "parking": True, "elevator": True, "shareable": True,
            "student_only": True, "senior_friendly": True,
            "social_housing": True, "newbuild": True,
            "electric_charging_station": True, "dishwasher": True,
            "washing_machine": True, "dryer": True,
        }
        config = SearchConfig.from_dict(all_bools)
        body = config.to_api_body()
        for key in all_bools:
            assert body[key] is True, f"{key} should be True in API body"

    def test_boolean_filters_excluded_when_none(self) -> None:
        config = SearchConfig.from_dict({})
        body = config.to_api_body()
        for key in ["pet_friendly", "balcony", "social_housing", "newbuild",
                     "electric_charging_station", "dishwasher", "washing_machine", "dryer"]:
            assert key not in body, f"{key} should not be in API body when None"

    def test_none_filters_excluded_from_body(self) -> None:
        config = SearchConfig.from_dict({})
        body = config.to_api_body()
        assert "max_monthly_rent" not in body
        assert "rooms" not in body
        assert "min_size_m2" not in body
        assert "min_rental_period" not in body
        assert "max_available_from" not in body
