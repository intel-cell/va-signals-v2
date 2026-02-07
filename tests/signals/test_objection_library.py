"""Tests for Objection Library.

CHARLIE COMMAND - Phase 4: Objection Library validation.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.signals.impact.models import IssueArea, SourceType
from src.signals.impact.objection_library import (
    ACCREDITATION_OBJECTIONS,
    APPROPRIATIONS_OBJECTIONS,
    BENEFITS_OBJECTIONS,
    ObjectionLibrary,
    find_objection_response,
    get_objections_for_area,
    render_objection_for_brief,
    seed_objection_library,
)


class TestSeedData:
    """Test the seed data content."""

    def test_benefits_objections_count(self):
        """Test that benefits has 10 objections."""
        assert len(BENEFITS_OBJECTIONS) == 10

    def test_accreditation_objections_count(self):
        """Test that accreditation has 10 objections."""
        assert len(ACCREDITATION_OBJECTIONS) == 10

    def test_appropriations_objections_count(self):
        """Test that appropriations has 10 objections."""
        assert len(APPROPRIATIONS_OBJECTIONS) == 10

    def test_total_seed_objections(self):
        """Test total seed objections is 30+."""
        total = (
            len(BENEFITS_OBJECTIONS)
            + len(ACCREDITATION_OBJECTIONS)
            + len(APPROPRIATIONS_OBJECTIONS)
        )
        assert total >= 30

    def test_objection_id_format(self):
        """Test objection IDs follow format OBJ-XXX-NNN."""
        all_objections = BENEFITS_OBJECTIONS + ACCREDITATION_OBJECTIONS + APPROPRIATIONS_OBJECTIONS
        for obj in all_objections:
            assert obj["objection_id"].startswith("OBJ-")
            parts = obj["objection_id"].split("-")
            assert len(parts) == 3
            assert parts[1] in ("BEN", "ACC", "APP")

    def test_objection_text_not_empty(self):
        """Test all objections have text."""
        all_objections = BENEFITS_OBJECTIONS + ACCREDITATION_OBJECTIONS + APPROPRIATIONS_OBJECTIONS
        for obj in all_objections:
            assert len(obj["objection_text"]) >= 10
            assert len(obj["response_text"]) >= 10

    def test_objection_source_types(self):
        """Test source types are valid."""
        valid_types = {
            SourceType.STAFF,
            SourceType.VSO,
            SourceType.INDUSTRY,
            SourceType.MEDIA,
            SourceType.CONGRESSIONAL,
            SourceType.VA_INTERNAL,
        }
        all_objections = BENEFITS_OBJECTIONS + ACCREDITATION_OBJECTIONS + APPROPRIATIONS_OBJECTIONS
        for obj in all_objections:
            assert obj["source_type"] in valid_types


class TestBenefitsObjections:
    """Test benefits-specific objections."""

    def test_covers_backlog_concern(self):
        """Test backlog objection exists."""
        texts = [o["objection_text"].lower() for o in BENEFITS_OBJECTIONS]
        assert any("backlog" in t for t in texts)

    def test_covers_staffing_concern(self):
        """Test staffing objection exists."""
        texts = [o["objection_text"].lower() for o in BENEFITS_OBJECTIONS]
        assert any("staff" in t for t in texts)

    def test_covers_vso_concern(self):
        """Test VSO objection exists."""
        texts = [o["objection_text"].lower() for o in BENEFITS_OBJECTIONS]
        assert any("vso" in t for t in texts)

    def test_covers_it_systems(self):
        """Test IT systems objection exists."""
        texts = [o["objection_text"].lower() for o in BENEFITS_OBJECTIONS]
        assert any("system" in t or "it" in t for t in texts)


class TestAccreditationObjections:
    """Test accreditation-specific objections."""

    def test_covers_burden_concern(self):
        """Test regulatory burden objection exists."""
        texts = [o["objection_text"].lower() for o in ACCREDITATION_OBJECTIONS]
        assert any("burden" in t for t in texts)

    def test_covers_fee_concern(self):
        """Test fee restriction objection exists."""
        texts = [o["objection_text"].lower() for o in ACCREDITATION_OBJECTIONS]
        assert any("fee" in t for t in texts)

    def test_covers_access_concern(self):
        """Test access to representation objection exists."""
        texts = [o["objection_text"].lower() for o in ACCREDITATION_OBJECTIONS]
        assert any("access" in t or "representation" in t for t in texts)


class TestAppropriationsObjections:
    """Test appropriations-specific objections."""

    def test_covers_spending_caps(self):
        """Test spending caps objection exists."""
        texts = [o["objection_text"].lower() for o in APPROPRIATIONS_OBJECTIONS]
        assert any("cap" in t or "spending" in t for t in texts)

    def test_covers_execution(self):
        """Test budget execution objection exists."""
        texts = [o["objection_text"].lower() for o in APPROPRIATIONS_OBJECTIONS]
        assert any("spent" in t or "efficient" in t for t in texts)

    def test_covers_cost_estimates(self):
        """Test cost estimate objection exists."""
        texts = [o["objection_text"].lower() for o in APPROPRIATIONS_OBJECTIONS]
        assert any("cost" in t or "estimate" in t for t in texts)


class TestObjectionLibraryClass:
    """Test ObjectionLibrary class."""

    @pytest.fixture
    def library(self):
        return ObjectionLibrary()

    def test_instantiation(self, library):
        """Test library can be instantiated."""
        assert library is not None
        assert library._seed_data_loaded is False

    @patch("src.signals.impact.objection_library.get_objection_stats")
    @patch("src.signals.impact.objection_library.insert_objection")
    def test_seed_database(self, mock_insert, mock_stats, library):
        """Test seed_database inserts objections."""
        mock_stats.return_value = {"total": 0}
        mock_insert.return_value = "OBJ-TEST-001"

        count = library.seed_database()

        assert count == 30  # 10 + 10 + 10
        assert mock_insert.call_count == 30

    @patch("src.signals.impact.objection_library.get_objection_stats")
    def test_seed_database_skips_if_populated(self, mock_stats, library):
        """Test seed_database skips if already populated."""
        mock_stats.return_value = {"total": 30}

        count = library.seed_database()

        assert count == 0

    @patch("src.signals.impact.objection_library.search_objections")
    def test_find_response(self, mock_search, library):
        """Test find_response returns best match."""
        mock_search.return_value = [
            {
                "objection_id": "OBJ-BEN-001",
                "issue_area": "benefits",
                "objection_text": "Test objection",
                "response_text": "Test response",
            }
        ]

        result = library.find_response("backlog concerns")

        assert result is not None
        assert result["objection_id"] == "OBJ-BEN-001"

    @patch("src.signals.impact.objection_library.search_objections")
    def test_find_response_filters_by_area(self, mock_search, library):
        """Test find_response filters by issue area."""
        mock_search.return_value = [
            {"objection_id": "OBJ-BEN-001", "issue_area": "benefits"},
            {"objection_id": "OBJ-ACC-001", "issue_area": "accreditation"},
        ]

        result = library.find_response("test", issue_area=IssueArea.ACCREDITATION)

        assert result["objection_id"] == "OBJ-ACC-001"

    @patch("src.signals.impact.objection_library.get_objections")
    def test_get_by_area(self, mock_get, library):
        """Test get_by_area filters correctly."""
        mock_get.return_value = [{"objection_id": "OBJ-BEN-001"}]

        results = library.get_by_area(IssueArea.BENEFITS)

        mock_get.assert_called_once_with(issue_area="benefits", limit=10)
        assert len(results) == 1

    @patch("src.signals.impact.objection_library.get_objections")
    def test_get_by_source(self, mock_get, library):
        """Test get_by_source filters correctly."""
        mock_get.return_value = [{"objection_id": "OBJ-BEN-001"}]

        library.get_by_source(SourceType.CONGRESSIONAL)

        mock_get.assert_called_once_with(source_type="congressional", limit=10)

    @patch("src.signals.impact.objection_library.update_objection_usage")
    def test_record_usage(self, mock_update, library):
        """Test record_usage updates database."""
        library.record_usage("OBJ-BEN-001", effectiveness=4)

        mock_update.assert_called_once_with("OBJ-BEN-001", 4)

    @patch("src.signals.impact.objection_library.insert_objection")
    def test_add_objection(self, mock_insert, library):
        """Test add_objection creates new entry."""
        mock_insert.return_value = "OBJ-BEN-NEW123"

        objection_id = library.add_objection(
            issue_area=IssueArea.BENEFITS,
            source_type=SourceType.STAFF,
            objection_text="New objection",
            response_text="New response",
        )

        assert objection_id.startswith("OBJ-BEN-")
        mock_insert.assert_called_once()


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    @patch("src.signals.impact.objection_library.ObjectionLibrary")
    def test_seed_objection_library(self, mock_class):
        """Test seed_objection_library convenience function."""
        mock_instance = MagicMock()
        mock_instance.seed_database.return_value = 30
        mock_class.return_value = mock_instance

        count = seed_objection_library()

        assert count == 30
        mock_instance.seed_database.assert_called_once_with(force=False)

    @patch("src.signals.impact.objection_library.ObjectionLibrary")
    def test_find_objection_response(self, mock_class):
        """Test find_objection_response convenience function."""
        mock_instance = MagicMock()
        mock_instance.find_response.return_value = {"objection_id": "OBJ-TEST"}
        mock_class.return_value = mock_instance

        result = find_objection_response("test objection")

        assert result["objection_id"] == "OBJ-TEST"

    @patch("src.signals.impact.objection_library.ObjectionLibrary")
    def test_get_objections_for_area(self, mock_class):
        """Test get_objections_for_area convenience function."""
        mock_instance = MagicMock()
        mock_instance.get_by_area.return_value = [{"objection_id": "OBJ-BEN-001"}]
        mock_class.return_value = mock_instance

        results = get_objections_for_area(IssueArea.BENEFITS)

        assert len(results) == 1


class TestRenderFunction:
    """Test rendering functions."""

    def test_render_objection_for_brief(self):
        """Test objection rendering for CEO Brief."""
        objection = {
            "objection_text": "This will increase the backlog.",
            "response_text": "Analysis shows this will actually reduce backlog by 15%.",
            "source_type": "staff",
            "issue_area": "benefits",
        }

        output = render_objection_for_brief(objection)

        assert "Objection:" in output
        assert "Response:" in output
        assert "backlog" in output
        assert "STAFF" in output
        assert "BENEFITS" in output
