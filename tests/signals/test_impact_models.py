"""Tests for Impact Translation models.

CHARLIE COMMAND - Phase 1: Impact Memo Schema validation.
"""

import pytest
from datetime import datetime

from src.signals.impact.models import (
    ImpactMemo,
    PolicyHook,
    WhyItMatters,
    HeatMap,
    HeatMapIssue,
    Objection,
    Posture,
    ConfidenceLevel,
    RiskLevel,
    IssueArea,
    SourceType,
    HeatMapQuadrant,
    create_impact_memo,
    create_heat_map_issue,
)


class TestImpactMemo:
    """Test ImpactMemo dataclass and schema compliance."""

    def test_create_impact_memo_factory(self):
        """Test factory function creates valid memo."""
        memo = create_impact_memo(
            issue_id="BILL-HR-1234",
            vehicle="H.R. 1234",
            vehicle_type="bill",
            current_status="introduced",
            source_url="https://congress.gov/bill/119/hr/1234",
            what_it_does="Requires VA to report claims processing times quarterly.",
            operational_impact="Adds reporting burden; may require new IT systems.",
            affected_workflows=["claims_intake", "rating"],
            compliance_exposure=RiskLevel.MEDIUM,
            reputational_risk=RiskLevel.LOW,
            posture=Posture.MONITOR,
            recommended_action="Track progress; prepare compliance plan if advances.",
            decision_trigger="If bill reaches committee markup, escalate to leadership.",
            confidence=ConfidenceLevel.MEDIUM,
            sources=["https://congress.gov/bill/119/hr/1234/text"],
        )

        assert memo.memo_id.startswith("MEMO-")
        assert memo.issue_id == "BILL-HR-1234"
        assert memo.policy_hook.vehicle == "H.R. 1234"
        assert memo.our_posture == Posture.MONITOR
        assert memo.confidence_level == ConfidenceLevel.MEDIUM

    def test_impact_memo_to_dict(self):
        """Test serialization matches expected schema."""
        policy_hook = PolicyHook(
            vehicle="RIN 2900-AQ66",
            vehicle_type="rule",
            section_reference="38 CFR 3.156",
            current_status="proposed_rule",
            source_url="https://federalregister.gov/d/2026-12345",
            effective_date="2026-07-01",
        )

        why_it_matters = WhyItMatters(
            operational_impact="Increases evidence requirements for claims.",
            affected_workflows=["claims_development", "medical_evidence"],
            affected_veteran_count="~500K annually",
            compliance_exposure=RiskLevel.HIGH,
            enforcement_mechanism="OIG audit",
            compliance_deadline="2026-07-01",
            cost_impact="$3-5M implementation",
            cost_type="it",
            reputational_risk=RiskLevel.MEDIUM,
            narrative_vulnerability="VSOs may claim VA raising barriers",
        )

        memo = ImpactMemo(
            memo_id="MEMO-20260204-ABC12345",
            issue_id="RULE-2900-AQ66",
            generated_date="2026-02-04T10:00:00Z",
            policy_hook=policy_hook,
            what_it_does="Revises evidence requirements for reopening previously denied claims.",
            why_it_matters=why_it_matters,
            our_posture=Posture.OPPOSE,
            recommended_action="Submit public comment opposing increased burden.",
            decision_trigger="If final rule published, file for reconsideration.",
            confidence_level=ConfidenceLevel.HIGH,
            sources=["https://federalregister.gov/d/2026-12345"],
        )

        d = memo.to_dict()

        assert d["memo_id"] == "MEMO-20260204-ABC12345"
        assert d["policy_hook"]["vehicle"] == "RIN 2900-AQ66"
        assert d["why_it_matters"]["compliance_exposure"] == "high"
        assert d["our_posture"] == "oppose"
        assert "claims_development" in d["why_it_matters"]["affected_workflows"]


class TestHeatMap:
    """Test HeatMap and HeatMapIssue."""

    def test_score_calculation(self):
        """Test priority score calculation with urgency factor."""
        # Urgent (7 days) - 2x factor
        score_urgent = HeatMapIssue.calculate_score(likelihood=4, impact=5, urgency_days=5)
        assert score_urgent == 4 * 5 * 2.0  # 40

        # Near-term (14 days) - 1.5x factor
        score_near = HeatMapIssue.calculate_score(likelihood=4, impact=5, urgency_days=10)
        assert score_near == 4 * 5 * 1.5  # 30

        # Medium-term (30 days) - 1.2x factor
        score_medium = HeatMapIssue.calculate_score(likelihood=4, impact=5, urgency_days=20)
        assert score_medium == 4 * 5 * 1.2  # 24

        # Long-term (60 days) - 1.0x factor
        score_long = HeatMapIssue.calculate_score(likelihood=4, impact=5, urgency_days=60)
        assert score_long == 4 * 5 * 1.0  # 20

    def test_quadrant_determination(self):
        """Test heat map quadrant logic."""
        # High likelihood (4), High impact (5) -> HIGH_PRIORITY
        assert HeatMapIssue.determine_quadrant(4, 5) == HeatMapQuadrant.HIGH_PRIORITY

        # Low likelihood (2), High impact (4) -> WATCH
        assert HeatMapIssue.determine_quadrant(2, 4) == HeatMapQuadrant.WATCH

        # High likelihood (4), Low impact (2) -> MONITOR
        assert HeatMapIssue.determine_quadrant(4, 2) == HeatMapQuadrant.MONITOR

        # Low likelihood (2), Low impact (2) -> LOW
        assert HeatMapIssue.determine_quadrant(2, 2) == HeatMapQuadrant.LOW

        # Boundary case: likelihood=3, impact=3 -> HIGH_PRIORITY
        assert HeatMapIssue.determine_quadrant(3, 3) == HeatMapQuadrant.HIGH_PRIORITY

    def test_create_heat_map_issue_factory(self):
        """Test factory function creates issue with calculated fields."""
        issue = create_heat_map_issue(
            issue_id="BILL-HR-5678",
            title="VA Claims Modernization Act",
            likelihood=4,
            impact=4,
            urgency_days=10,
        )

        assert issue.issue_id == "BILL-HR-5678"
        assert issue.score == 4 * 4 * 1.5  # 24 (10 days = 1.5x)
        assert issue.quadrant == HeatMapQuadrant.HIGH_PRIORITY

    def test_heat_map_to_dict(self):
        """Test heat map serialization."""
        issues = [
            create_heat_map_issue("ISS-001", "High Priority Item", 5, 5, 3),
            create_heat_map_issue("ISS-002", "Watch Item", 2, 4, 30),
            create_heat_map_issue("ISS-003", "Monitor Item", 4, 2, 60),
        ]

        heat_map = HeatMap(
            heat_map_id="HMAP-20260204-ABC12345",
            generated_date="2026-02-04T10:00:00Z",
            issues=issues,
        )

        d = heat_map.to_dict()

        assert d["heat_map_id"] == "HMAP-20260204-ABC12345"
        assert len(d["issues"]) == 3
        assert d["summary"]["total_issues"] == 3
        assert d["summary"]["high_priority_count"] == 1

    def test_heat_map_get_high_priority(self):
        """Test filtering high priority issues."""
        issues = [
            create_heat_map_issue("ISS-001", "High 1", 5, 5, 3),
            create_heat_map_issue("ISS-002", "Low", 2, 2, 30),
            create_heat_map_issue("ISS-003", "High 2", 4, 4, 5),
        ]

        heat_map = HeatMap(
            heat_map_id="HMAP-TEST",
            generated_date="2026-02-04T10:00:00Z",
            issues=issues,
        )

        high_priority = heat_map.get_high_priority()
        assert len(high_priority) == 2
        # Should be sorted by score descending
        assert high_priority[0].score >= high_priority[1].score

    def test_heat_map_ascii_render(self):
        """Test ASCII visualization."""
        issues = [
            create_heat_map_issue("ISS-001", "Critical Legislation", 5, 5, 3),
            create_heat_map_issue("ISS-002", "Regulatory Watch", 2, 4, 30),
        ]

        heat_map = HeatMap(
            heat_map_id="HMAP-TEST",
            generated_date="2026-02-04T10:00:00Z",
            issues=issues,
        )

        ascii_output = heat_map.render_ascii()
        assert "HIGH IMPACT" in ascii_output
        assert "HIGH PRIORITY" in ascii_output
        assert "WATCH" in ascii_output


class TestObjection:
    """Test Objection dataclass."""

    def test_objection_to_dict(self):
        """Test objection serialization."""
        objection = Objection(
            objection_id="OBJ-BEN-001",
            issue_area=IssueArea.BENEFITS,
            source_type=SourceType.STAFF,
            objection_text="This will increase the backlog significantly.",
            response_text="Data shows 90% of claims affected are already delayed; this expedites resolution.",
            supporting_evidence=["https://va.gov/stats/2026-q1"],
            effectiveness_rating=4,
            tags=["backlog", "claims_processing"],
        )

        d = objection.to_dict()

        assert d["objection_id"] == "OBJ-BEN-001"
        assert d["issue_area"] == "benefits"
        assert d["source_type"] == "staff"
        assert d["effectiveness_rating"] == 4
        assert "backlog" in d["tags"]


class TestEnumerations:
    """Test enumeration values match schema."""

    def test_posture_values(self):
        """Test Posture enum values."""
        assert Posture.SUPPORT.value == "support"
        assert Posture.OPPOSE.value == "oppose"
        assert Posture.MONITOR.value == "monitor"
        assert Posture.NEUTRAL_ENGAGED.value == "neutral_engaged"

    def test_confidence_level_values(self):
        """Test ConfidenceLevel enum values."""
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.LOW.value == "low"

    def test_risk_level_values(self):
        """Test RiskLevel enum values."""
        assert RiskLevel.CRITICAL.value == "critical"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.NEGLIGIBLE.value == "negligible"

    def test_issue_area_values(self):
        """Test IssueArea enum values."""
        assert IssueArea.BENEFITS.value == "benefits"
        assert IssueArea.ACCREDITATION.value == "accreditation"
        assert IssueArea.APPROPRIATIONS.value == "appropriations"
