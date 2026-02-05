"""Tests for CHARLIE COMMAND Phase 5: Inter-Command Integrations.

Tests cover:
- DELTA integration (heat scores to battlefield dashboard)
- ALPHA integration (impact content for CEO Brief)
- BRAVO integration (evidence pack enrichment)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from src.signals.impact.integrations import (
    # DELTA
    push_heat_scores_to_delta,
    batch_push_heat_scores,
    get_vehicles_needing_heat_scores,
    _issue_id_to_vehicle_id,
    # ALPHA
    get_impact_section_for_brief,
    get_risks_for_brief,
    get_objections_for_brief,
    _score_to_likelihood,
    _score_to_impact,
    _vehicle_type_to_source_type,
    # BRAVO
    enrich_memo_with_evidence,
    find_evidence_for_source,
    get_citations_for_topic,
    # Pipeline
    run_charlie_integration,
    check_integration_status,
)
from src.signals.impact.models import (
    HeatMap,
    HeatMapIssue,
    HeatMapQuadrant,
    create_heat_map_issue,
)


# =============================================================================
# ISSUE ID TO VEHICLE ID CONVERSION TESTS
# =============================================================================

class TestIssueIdToVehicleId:
    """Test CHARLIE to DELTA ID format conversion."""

    def test_bill_conversion(self):
        """Test BILL- prefix converts to bill_ prefix."""
        assert _issue_id_to_vehicle_id("BILL-hr-119-1234") == "bill_hr-119-1234"

    def test_hearing_conversion(self):
        """Test HEARING- prefix converts to hearing_ prefix."""
        assert _issue_id_to_vehicle_id("HEARING-118920") == "hearing_118920"

    def test_fr_conversion(self):
        """Test FR- prefix converts to fr_FR- format."""
        assert _issue_id_to_vehicle_id("FR-2026-01234") == "fr_FR-2026-01234"

    def test_memo_passthrough(self):
        """Test MEMO- prefix passes through unchanged."""
        assert _issue_id_to_vehicle_id("MEMO-20260204-ABC123") == "MEMO-20260204-ABC123"

    def test_generic_lowercase(self):
        """Test unknown formats get lowercased and hyphen-to-underscore."""
        assert _issue_id_to_vehicle_id("CUSTOM-FORMAT") == "custom_format"


# =============================================================================
# SCORE CONVERSION TESTS
# =============================================================================

class TestScoreConversions:
    """Test CHARLIE score to ALPHA enum conversions."""

    def test_likelihood_high(self):
        """Score 4-5 maps to high likelihood."""
        assert _score_to_likelihood(5) == "high"
        assert _score_to_likelihood(4) == "high"

    def test_likelihood_medium(self):
        """Score 2-3 maps to medium likelihood."""
        assert _score_to_likelihood(3) == "medium"
        assert _score_to_likelihood(2) == "medium"

    def test_likelihood_low(self):
        """Score 1 maps to low likelihood."""
        assert _score_to_likelihood(1) == "low"

    def test_impact_high(self):
        """Score 4-5 maps to high impact."""
        assert _score_to_impact(5) == "high"
        assert _score_to_impact(4) == "high"

    def test_impact_medium(self):
        """Score 2-3 maps to medium impact."""
        assert _score_to_impact(3) == "medium"
        assert _score_to_impact(2) == "medium"

    def test_impact_low(self):
        """Score 1 maps to low impact."""
        assert _score_to_impact(1) == "low"


class TestVehicleTypeToSourceType:
    """Test vehicle type to source type mapping."""

    def test_bill_maps_to_bill(self):
        assert _vehicle_type_to_source_type("bill") == "bill"

    def test_rule_maps_to_federal_register(self):
        assert _vehicle_type_to_source_type("rule") == "federal_register"

    def test_hearing_maps_to_hearing(self):
        assert _vehicle_type_to_source_type("hearing") == "hearing"

    def test_report_maps_to_gao(self):
        assert _vehicle_type_to_source_type("report") == "gao"

    def test_executive_order_maps_to_federal_register(self):
        assert _vehicle_type_to_source_type("executive_order") == "federal_register"

    def test_unknown_defaults_to_federal_register(self):
        assert _vehicle_type_to_source_type("unknown") == "federal_register"


# =============================================================================
# DELTA INTEGRATION TESTS
# =============================================================================

class TestDeltaIntegration:
    """Test DELTA battlefield dashboard integration."""

    def test_push_heat_scores_no_table(self):
        """Test graceful handling when DELTA tables don't exist."""
        heat_map = HeatMap(
            heat_map_id="HMAP-TEST-001",
            generated_date="2026-02-04T20:00:00Z",
            issues=[
                create_heat_map_issue("BILL-hr-119-1234", "Test Bill", 4, 4, 14),
            ],
        )

        with patch("src.signals.impact.integrations.connect") as mock_connect:
            mock_con = MagicMock()
            mock_connect.return_value = mock_con

            with patch("src.signals.impact.integrations.table_exists") as mock_exists:
                mock_exists.return_value = False

                result = push_heat_scores_to_delta(heat_map)

                assert result["updated"] == 0
                assert "bf_vehicles table not found" in result["errors"][0]

    def test_batch_push_invalid_entries(self):
        """Test batch push handles invalid entries."""
        scores = [
            {"vehicle_id": "valid_id", "heat_score": 85.0},
            {"vehicle_id": None, "heat_score": 50.0},  # Invalid
            {"heat_score": 60.0},  # Missing vehicle_id
        ]

        with patch("src.signals.impact.integrations.connect") as mock_connect:
            mock_con = MagicMock()
            mock_connect.return_value = mock_con

            with patch("src.signals.impact.integrations.table_exists") as mock_exists:
                mock_exists.return_value = False

                result = batch_push_heat_scores(scores)

                assert "bf_vehicles table not found" in result["errors"][0]

    def test_get_vehicles_needing_scores_no_table(self):
        """Test get vehicles handles missing DELTA tables."""
        with patch("src.signals.impact.integrations.connect") as mock_connect:
            mock_con = MagicMock()
            mock_connect.return_value = mock_con

            with patch("src.signals.impact.integrations.table_exists") as mock_exists:
                mock_exists.return_value = False

                result = get_vehicles_needing_heat_scores()

                assert result == []


# =============================================================================
# ALPHA INTEGRATION TESTS
# =============================================================================

class TestAlphaIntegration:
    """Test ALPHA CEO Brief integration."""

    def test_get_impact_section_structure(self):
        """Test impact section returns expected structure."""
        with patch("src.signals.impact.integrations.get_high_priority_issues") as mock_hp:
            mock_hp.return_value = [
                {
                    "issue_id": "BILL-hr-119-1234",
                    "title": "Test Bill",
                    "likelihood": 4,
                    "impact": 4,
                    "score": 32.0,
                    "quadrant": "high_priority",
                    "memo_id": None,
                }
            ]

            with patch("src.signals.impact.integrations.get_objections") as mock_obj:
                mock_obj.return_value = [
                    {
                        "objection_text": "This will increase backlog",
                        "response_text": "Analysis shows otherwise",
                        "supporting_evidence": [],
                    }
                ]

                with patch("src.signals.impact.integrations.get_current_heat_map") as mock_hm:
                    mock_hm.return_value = None

                    with patch("src.signals.impact.integrations._get_memo_for_issue") as mock_memo:
                        mock_memo.return_value = None

                        result = get_impact_section_for_brief()

                        assert "risks_opportunities" in result
                        assert "objections_responses" in result
                        assert "heat_map_text" in result
                        assert len(result["risks_opportunities"]) == 1
                        assert len(result["objections_responses"]) == 1

    def test_get_risks_for_brief_format(self):
        """Test risks format matches ALPHA RiskOpportunity schema."""
        with patch("src.signals.impact.integrations.get_high_priority_issues") as mock_hp:
            mock_hp.return_value = [
                {
                    "issue_id": "BILL-hr-119-1234",
                    "title": "Veterans Benefits Reform",
                    "likelihood": 5,
                    "impact": 4,
                    "score": 40.0,
                    "quadrant": "high_priority",
                    "memo_id": "MEMO-001",
                }
            ]

            with patch("src.signals.impact.integrations._get_memo_for_issue") as mock_memo:
                mock_memo.return_value = {
                    "recommended_action": "Monitor committee markup",
                    "policy_hook": {
                        "vehicle": "H.R. 1234",
                        "vehicle_type": "bill",
                        "source_url": "https://congress.gov/...",
                        "effective_date": "2026-03-01",
                    },
                    "what_it_does": "Expands veteran benefits eligibility",
                }

                risks = get_risks_for_brief(limit=1)

                assert len(risks) == 1
                risk = risks[0]

                # Check ALPHA RiskOpportunity schema compliance
                assert "description" in risk
                assert "is_risk" in risk
                assert "likelihood" in risk
                assert "impact" in risk
                assert "mitigation_or_action" in risk
                assert "supporting_citations" in risk

                assert risk["likelihood"] == "high"
                assert risk["impact"] == "high"
                assert risk["mitigation_or_action"] == "Monitor committee markup"

    def test_get_objections_for_brief_format(self):
        """Test objections format matches ALPHA ObjectionResponse schema."""
        with patch("src.signals.impact.integrations.get_objections") as mock_obj:
            mock_obj.return_value = [
                {
                    "objection_text": "VSOs are opposed to this",
                    "response_text": "We've consulted with major VSOs...",
                    "supporting_evidence": ["VSO consultation notes"],
                }
            ]

            objections = get_objections_for_brief(limit=1)

            assert len(objections) == 1
            obj = objections[0]

            # Check ALPHA ObjectionResponse schema compliance
            assert "objection" in obj
            assert "response" in obj
            assert "supporting_citations" in obj

            assert obj["objection"] == "VSOs are opposed to this"
            assert "consulted with major VSOs" in obj["response"]


# =============================================================================
# BRAVO INTEGRATION TESTS
# =============================================================================

class TestBravoIntegration:
    """Test BRAVO evidence pack integration."""

    def test_enrich_memo_no_table(self):
        """Test evidence enrichment handles missing BRAVO tables."""
        with patch("src.signals.impact.integrations.connect") as mock_connect:
            mock_con = MagicMock()
            mock_connect.return_value = mock_con

            with patch("src.signals.impact.integrations.table_exists") as mock_exists:
                mock_exists.return_value = False

                result = enrich_memo_with_evidence("MEMO-001", "ISSUE-001")

                assert result is None

    def test_find_evidence_no_table(self):
        """Test evidence search handles missing BRAVO tables."""
        with patch("src.signals.impact.integrations.connect") as mock_connect:
            mock_con = MagicMock()
            mock_connect.return_value = mock_con

            with patch("src.signals.impact.integrations.table_exists") as mock_exists:
                mock_exists.return_value = False

                result = find_evidence_for_source("bill", "hr-119-1234")

                assert result is None

    def test_get_citations_no_table(self):
        """Test citation search handles missing BRAVO tables."""
        with patch("src.signals.impact.integrations.connect") as mock_connect:
            mock_con = MagicMock()
            mock_connect.return_value = mock_con

            with patch("src.signals.impact.integrations.table_exists") as mock_exists:
                mock_exists.return_value = False

                result = get_citations_for_topic("veteran benefits")

                assert result == []


# =============================================================================
# INTEGRATION PIPELINE TESTS
# =============================================================================

class TestIntegrationPipeline:
    """Test full integration pipeline."""

    def test_run_charlie_integration_structure(self):
        """Test integration run returns expected structure."""
        with patch("src.signals.impact.heat_map_generator.generate_heat_map") as mock_gen:
            mock_hm = MagicMock()
            mock_hm.heat_map_id = "HMAP-TEST"
            mock_hm.issues = []
            mock_hm.to_dict.return_value = {"heat_map_id": "HMAP-TEST", "issues": []}
            mock_gen.return_value = mock_hm

            with patch.object(
                __import__("src.signals.impact.integrations", fromlist=["push_heat_scores_to_delta"]),
                "push_heat_scores_to_delta"
            ) as mock_push:
                mock_push.return_value = {"updated": 0, "not_found": 0, "errors": [], "heat_map_id": "HMAP-TEST"}

                with patch.object(
                    __import__("src.signals.impact.integrations", fromlist=["get_impact_section_for_brief"]),
                    "get_impact_section_for_brief"
                ) as mock_brief:
                    mock_brief.return_value = {
                        "risks_opportunities": [],
                        "objections_responses": [],
                        "heat_map_text": "",
                    }

                    result = run_charlie_integration()

                    assert "timestamp" in result
                    assert "delta_sync" in result
                    assert "alpha_content" in result
                    assert "errors" in result

    def test_check_integration_status(self):
        """Test integration status check."""
        with patch("src.signals.impact.integrations.connect") as mock_connect:
            mock_con = MagicMock()
            mock_connect.return_value = mock_con

            with patch("src.signals.impact.integrations.table_exists") as mock_exists:
                # Simulate DELTA exists but BRAVO doesn't
                mock_exists.side_effect = lambda con, table: table == "bf_vehicles"

                with patch("src.signals.impact.integrations.get_latest_heat_map") as mock_hm:
                    mock_hm.return_value = {
                        "heat_map_id": "HMAP-001",
                        "issues": [{"issue_id": "1"}, {"issue_id": "2"}],
                    }

                    with patch("src.signals.impact.integrations.get_impact_memos") as mock_memos:
                        mock_memos.return_value = [{"memo_id": "MEMO-001"}]

                        with patch("src.signals.impact.integrations.get_objections") as mock_obj:
                            mock_obj.return_value = [{"objection_id": "OBJ-001"}]

                            status = check_integration_status()

                            assert status["charlie_ready"] is True
                            assert status["delta_connected"] is True
                            assert status["bravo_connected"] is False
                            assert status["alpha_ready"] is True
                            assert status["heat_map_available"] is True
                            assert status["heat_map_issues_count"] == 2


# =============================================================================
# HEAT MAP TO DELTA FORMAT TESTS
# =============================================================================

class TestHeatMapToDeltaFormat:
    """Test heat map data conversion for DELTA."""

    def test_heat_map_issue_to_delta_score(self):
        """Test HeatMapIssue score converts correctly for DELTA."""
        issue = create_heat_map_issue(
            issue_id="BILL-hr-119-1234",
            title="Test Bill",
            likelihood=4,
            impact=5,
            urgency_days=7,
        )

        # Score should be likelihood * impact * urgency_factor
        # 4 * 5 * 2.0 (7 days = 2x factor) = 40.0
        assert issue.score == 40.0

        # Vehicle ID conversion
        vehicle_id = _issue_id_to_vehicle_id(issue.issue_id)
        assert vehicle_id == "bill_hr-119-1234"

    def test_full_heat_map_conversion(self):
        """Test full heat map converts to DELTA-compatible format."""
        heat_map = HeatMap(
            heat_map_id="HMAP-20260204-ABC123",
            generated_date="2026-02-04T20:00:00Z",
            issues=[
                create_heat_map_issue("BILL-hr-119-1234", "Benefits Reform", 5, 5, 5),
                create_heat_map_issue("HEARING-118920", "Oversight Hearing", 3, 4, 14),
                create_heat_map_issue("FR-2026-01234", "New Regulation", 4, 3, 30),
            ],
        )

        # Verify conversions
        assert len(heat_map.issues) == 3

        # Check high priority issue
        high_priority = heat_map.get_high_priority()
        assert len(high_priority) >= 1

        # Verify vehicle ID conversions work
        for issue in heat_map.issues:
            vehicle_id = _issue_id_to_vehicle_id(issue.issue_id)
            assert vehicle_id is not None
            assert len(vehicle_id) > 0
