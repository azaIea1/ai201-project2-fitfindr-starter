"""
tests/test_tools.py

Pytest tests for each FitFindr tool, covering happy paths and all failure modes.
Run with: pytest tests/
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

class TestSearchListings:
    def test_returns_results_for_valid_query(self):
        results = search_listings("vintage graphic tee", size=None, max_price=50)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_returns_empty_list_no_exception_when_nothing_matches(self):
        # Impossible query — should return [] not raise
        results = search_listings("designer ballgown", size="XXS", max_price=5)
        assert results == []

    def test_price_filter_respected(self):
        results = search_listings("jacket", size=None, max_price=20)
        assert all(item["price"] <= 20 for item in results)

    def test_size_filter_case_insensitive(self):
        results = search_listings("shirt", size="m", max_price=None)
        # Every result should contain 'm' in its size field (case-insensitive)
        assert all("m" in item["size"].lower() for item in results)

    def test_results_sorted_best_match_first(self):
        results = search_listings("vintage denim jeans", size=None, max_price=None)
        assert len(results) > 0
        # First result should have "vintage" or "denim" or "jeans" in its fields
        first = results[0]
        searchable = (
            first["title"] + " " + first["description"] + " " +
            " ".join(first["style_tags"])
        ).lower()
        assert any(kw in searchable for kw in ["vintage", "denim", "jean"])

    def test_no_results_returns_empty_list_not_none(self):
        results = search_listings("xyzzy nonexistent item", size=None, max_price=None)
        assert results is not None
        assert isinstance(results, list)

    def test_all_returned_fields_present(self):
        results = search_listings("jacket", size=None, max_price=200)
        if results:
            required_fields = {"id", "title", "description", "category",
                               "style_tags", "size", "condition", "price",
                               "colors", "platform"}
            for item in results:
                assert required_fields.issubset(item.keys())


# ── suggest_outfit ────────────────────────────────────────────────────────────

class TestSuggestOutfit:
    def setup_method(self):
        """Get a real listing to use as new_item in tests."""
        results = search_listings("vintage graphic tee", size=None, max_price=50)
        self.item = results[0] if results else {
            "id": "test_001",
            "title": "Test Tee",
            "category": "tops",
            "colors": ["black"],
            "style_tags": ["vintage", "graphic tee"],
            "condition": "good",
            "price": 22.0,
            "platform": "depop",
            "brand": None,
        }

    def test_returns_non_empty_string_with_wardrobe(self):
        result = suggest_outfit(self.item, get_example_wardrobe())
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_returns_non_empty_string_with_empty_wardrobe(self):
        # Must not crash or return empty string with empty wardrobe
        result = suggest_outfit(self.item, get_empty_wardrobe())
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_empty_wardrobe_does_not_raise(self):
        # This is the key failure-mode test
        try:
            result = suggest_outfit(self.item, get_empty_wardrobe())
            assert result  # must be truthy
        except Exception as e:
            pytest.fail(f"suggest_outfit raised an exception on empty wardrobe: {e}")


# ── create_fit_card ───────────────────────────────────────────────────────────

class TestCreateFitCard:
    def setup_method(self):
        results = search_listings("vintage graphic tee", size=None, max_price=50)
        self.item = results[0] if results else {
            "id": "test_001",
            "title": "Test Tee",
            "category": "tops",
            "colors": ["black"],
            "style_tags": ["vintage", "graphic tee"],
            "condition": "good",
            "price": 22.0,
            "platform": "depop",
            "brand": None,
        }
        self.outfit = "Pair with baggy dark wash jeans and chunky white sneakers for a 90s vibe."

    def test_returns_string_for_valid_inputs(self):
        result = create_fit_card(self.outfit, self.item)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_empty_outfit_returns_error_message_not_exception(self):
        # Key failure mode — must not crash
        result = create_fit_card("", self.item)
        assert isinstance(result, str)
        assert "cannot" in result.lower() or "missing" in result.lower() or "unavailable" in result.lower()

    def test_whitespace_only_outfit_returns_error_message(self):
        result = create_fit_card("   ", self.item)
        assert isinstance(result, str)
        assert len(result) > 0
        # Should be an error message, not a real caption
        assert "cannot" in result.lower() or "missing" in result.lower() or "unavailable" in result.lower()

    def test_empty_outfit_does_not_raise(self):
        try:
            result = create_fit_card("", self.item)
            assert result
        except Exception as e:
            pytest.fail(f"create_fit_card raised an exception on empty outfit: {e}")
