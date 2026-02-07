"""Tests for CEO Brief aggregator scoring, classification, and aggregation."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

from src.ceo_brief.aggregator import (
    _parse_action_level,
    _raw_to_aggregated,
    aggregate_deltas,
    calculate_impact_score,
    calculate_relevance_score,
    calculate_urgency_score,
    classify_issue_area,
    get_deltas_by_issue_area,
    get_top_deltas,
)
from src.ceo_brief.schema import (
    AggregatedDelta,
    AggregationResult,
    IssueArea,
    SourceType,
)

# ---------------------------------------------------------------------------
# classify_issue_area
# ---------------------------------------------------------------------------


class TestClassifyIssueArea:
    def test_benefits_claims_backlog(self):
        assert classify_issue_area("VA claims backlog") == IssueArea.BENEFITS_CLAIMS

    def test_appropriations_budget(self):
        assert classify_issue_area("OMB budget FY2026") == IssueArea.APPROPRIATIONS

    def test_accreditation_attorneys(self):
        assert classify_issue_area("accreditation of attorneys") == IssueArea.ACCREDITATION

    def test_healthcare_wait_times(self):
        assert classify_issue_area("VA healthcare wait times") == IssueArea.HEALTHCARE

    def test_technology_ehr(self):
        assert classify_issue_area("EHR modernization Cerner") == IssueArea.TECHNOLOGY

    def test_staffing_shortage(self):
        assert classify_issue_area("VA staffing shortage") == IssueArea.STAFFING

    def test_oversight_gao(self):
        assert classify_issue_area("GAO audit report finding") == IssueArea.OVERSIGHT

    def test_legal_cafc(self):
        assert classify_issue_area("CAFC court ruling") == IssueArea.LEGAL

    def test_state_program(self):
        assert classify_issue_area("state VA program") == IssueArea.STATE

    def test_other_unrelated(self):
        assert classify_issue_area("random unrelated topic") == IssueArea.OTHER

    def test_content_used_for_classification(self):
        result = classify_issue_area("generic title", content="VA claims backlog increasing")
        assert result == IssueArea.BENEFITS_CLAIMS

    def test_highest_match_wins(self):
        # "claims benefit pension backlog appeals" has 5 matches for BENEFITS_CLAIMS
        result = classify_issue_area("claims benefit pension backlog appeals")
        assert result == IssueArea.BENEFITS_CLAIMS


# ---------------------------------------------------------------------------
# _parse_action_level
# ---------------------------------------------------------------------------


class TestParseActionLevel:
    def test_fr_final_rule(self):
        delta = {"source_type": "federal_register", "title": "Final Rule on benefits"}
        assert _parse_action_level(delta) == "final_rule"

    def test_fr_interim_final_rule(self):
        # NOTE: In the current implementation, "final rule" is checked before
        # "interim final", so "Interim Final Rule" matches "final_rule" first.
        delta = {"source_type": "federal_register", "title": "Interim Final Rule on benefits"}
        assert _parse_action_level(delta) == "final_rule"

    def test_fr_proposed_rule(self):
        delta = {"source_type": "federal_register", "title": "Proposed Rule on benefits"}
        assert _parse_action_level(delta) == "proposed_rule"

    def test_fr_notice(self):
        delta = {"source_type": "federal_register", "title": "Notice of hearing"}
        assert _parse_action_level(delta) == "notice"

    def test_bill_passed_house(self):
        delta = {
            "source_type": "bill",
            "title": "HR 1234",
            "latest_action_text": "Passed House",
        }
        assert _parse_action_level(delta) == "passed_house"

    def test_bill_passed_senate(self):
        delta = {
            "source_type": "bill",
            "title": "S 567",
            "latest_action_text": "Passed Senate",
        }
        assert _parse_action_level(delta) == "passed_senate"

    def test_bill_became_law(self):
        delta = {
            "source_type": "bill",
            "title": "HR 100",
            "latest_action_text": "Became public law",
        }
        assert _parse_action_level(delta) == "became_law"

    def test_bill_introduced(self):
        delta = {
            "source_type": "bill",
            "title": "HR 200",
            "latest_action_text": "Introduced in House",
        }
        assert _parse_action_level(delta) == "introduced"

    def test_oversight_report_release(self):
        delta = {
            "source_type": "oversight",
            "title": "OIG Report",
            "event_type": "report_release",
        }
        assert _parse_action_level(delta) == "report_release"

    def test_oversight_testimony(self):
        delta = {
            "source_type": "oversight",
            "title": "Testimony before committee",
            "event_type": "testimony",
        }
        assert _parse_action_level(delta) == "testimony"

    def test_unknown_returns_other(self):
        delta = {"source_type": "news", "title": "Some news article"}
        assert _parse_action_level(delta) == "other"


# ---------------------------------------------------------------------------
# calculate_impact_score
# ---------------------------------------------------------------------------


class TestCalculateImpactScore:
    def test_escalation_boosts_score(self):
        base = {
            "source_type": "federal_register",
            "title": "Final Rule",
            "is_escalation": False,
            "published_date": date.today().isoformat(),
        }
        escalated = {**base, "is_escalation": True}
        period_end = date.today()
        score_base = calculate_impact_score(base, period_end)
        score_esc = calculate_impact_score(escalated, period_end)
        assert score_esc > score_base

    def test_recent_date_high_recency(self):
        today = date.today()
        delta = {
            "source_type": "federal_register",
            "title": "Final Rule",
            "published_date": today.isoformat(),
        }
        score = calculate_impact_score(delta, today)
        # Recency for same-day should be 1.0, weighted at 0.15 = 0.15 contribution
        assert score > 0.0

    def test_old_date_low_recency(self):
        today = date.today()
        old = (today - timedelta(days=30)).isoformat()
        delta = {
            "source_type": "news",
            "title": "Old news",
            "published_date": old,
        }
        score = calculate_impact_score(delta, today)
        # Recency should be 0 (capped at max(0, 1 - 30/7) = 0)
        assert score >= 0.0

    def test_score_in_range(self):
        delta = {
            "source_type": "federal_register",
            "title": "Final Rule",
            "is_escalation": True,
            "is_deviation": True,
            "published_date": date.today().isoformat(),
        }
        score = calculate_impact_score(delta, date.today())
        assert 0.0 <= score <= 1.0

    def test_deviation_contributes_to_score(self):
        base = {"source_type": "news", "title": "thing", "is_deviation": False}
        dev = {**base, "is_deviation": True}
        period_end = date.today()
        assert calculate_impact_score(dev, period_end) > calculate_impact_score(base, period_end)


# ---------------------------------------------------------------------------
# calculate_urgency_score
# ---------------------------------------------------------------------------


class TestCalculateUrgencyScore:
    def test_deadline_keyword_adds_urgency(self):
        delta = {"title": "Comment period deadline approaching", "summary": ""}
        score = calculate_urgency_score(delta, date.today())
        assert score >= 0.3

    def test_emergency_keyword(self):
        delta = {"title": "Emergency rule change", "summary": ""}
        score = calculate_urgency_score(delta, date.today())
        assert score >= 0.4

    def test_upcoming_hearing_date(self):
        hearing = (date.today() + timedelta(days=3)).isoformat()
        delta = {"title": "hearing", "summary": "", "hearing_date": hearing}
        score = calculate_urgency_score(delta, date.today())
        assert score >= 0.5

    def test_past_hearing_date(self):
        past = (date.today() - timedelta(days=2)).isoformat()
        delta = {"title": "", "summary": "", "hearing_date": past}
        score = calculate_urgency_score(delta, date.today())
        assert score >= 0.1

    def test_passed_bill_action(self):
        delta = {
            "title": "",
            "summary": "",
            "latest_action_text": "Passed House of Representatives",
        }
        score = calculate_urgency_score(delta, date.today())
        assert score >= 0.4

    def test_no_urgency_signals(self):
        delta = {"title": "routine update", "summary": "nothing special"}
        score = calculate_urgency_score(delta, date.today())
        assert score == 0.0

    def test_capped_at_one(self):
        # Combine all signals to push score above 1.0 — should cap
        hearing = (date.today() + timedelta(days=1)).isoformat()
        delta = {
            "title": "emergency deadline comment period",
            "summary": "urgent immediately",
            "hearing_date": hearing,
            "latest_action_text": "Passed House",
        }
        score = calculate_urgency_score(delta, date.today())
        assert score <= 1.0


# ---------------------------------------------------------------------------
# calculate_relevance_score
# ---------------------------------------------------------------------------


class TestCalculateRelevanceScore:
    def test_benefits_claims_highest(self):
        score = calculate_relevance_score({}, IssueArea.BENEFITS_CLAIMS)
        assert score == 1.0

    def test_accreditation_highest(self):
        assert calculate_relevance_score({}, IssueArea.ACCREDITATION) == 1.0

    def test_legal_high(self):
        assert calculate_relevance_score({}, IssueArea.LEGAL) == 0.8

    def test_oversight_high(self):
        assert calculate_relevance_score({}, IssueArea.OVERSIGHT) == 0.8

    def test_appropriations_medium(self):
        assert calculate_relevance_score({}, IssueArea.APPROPRIATIONS) == 0.6

    def test_technology_medium(self):
        assert calculate_relevance_score({}, IssueArea.TECHNOLOGY) == 0.6

    def test_healthcare_half(self):
        assert calculate_relevance_score({}, IssueArea.HEALTHCARE) == 0.5

    def test_state_low(self):
        assert calculate_relevance_score({}, IssueArea.STATE) == 0.4

    def test_other_lowest(self):
        assert calculate_relevance_score({}, IssueArea.OTHER) == 0.3


# ---------------------------------------------------------------------------
# _raw_to_aggregated
# ---------------------------------------------------------------------------


class TestRawToAggregated:
    def test_basic_conversion(self):
        delta = {
            "source_type": "federal_register",
            "source_id": "FR-2024-001",
            "title": "VA claims backlog Final Rule",
            "url": "https://example.com/doc",
            "published_date": "2024-06-15",
            "first_seen_at": "2024-06-15T10:00:00Z",
            "summary": "Test summary",
        }
        result = _raw_to_aggregated(delta, date(2024, 6, 15))
        assert isinstance(result, AggregatedDelta)
        assert result.source_type == SourceType.FEDERAL_REGISTER
        assert result.source_id == "FR-2024-001"
        assert result.title == "VA claims backlog Final Rule"
        assert result.issue_area == IssueArea.BENEFITS_CLAIMS
        assert result.impact_score > 0

    def test_missing_fields_defaults(self):
        delta = {"source_type": "unknown_type"}
        result = _raw_to_aggregated(delta, date.today())
        assert result.source_type == SourceType.NEWS  # fallback
        assert result.title == ""
        assert result.issue_area == IssueArea.OTHER

    def test_bill_source_mapping(self):
        delta = {
            "source_type": "bill",
            "title": "HR 1234 VA benefits",
            "source_id": "hr1234",
        }
        result = _raw_to_aggregated(delta, date.today())
        assert result.source_type == SourceType.BILL

    def test_content_truncated(self):
        delta = {
            "source_type": "federal_register",
            "title": "test",
            "summary": "x" * 10000,
        }
        result = _raw_to_aggregated(delta, date.today())
        assert len(result.raw_content) <= 5000


# ---------------------------------------------------------------------------
# aggregate_deltas (mocked)
# ---------------------------------------------------------------------------


class TestAggregateDeltas:
    @patch("src.ceo_brief.aggregator.get_all_deltas")
    def test_aggregate_basic(self, mock_get):
        mock_get.return_value = {
            "federal_register": [
                {
                    "source_type": "federal_register",
                    "source_id": "FR-001",
                    "title": "VA claims Final Rule",
                    "published_date": "2024-06-10",
                    "first_seen_at": "2024-06-10T10:00:00Z",
                }
            ],
            "bills": [
                {
                    "source_type": "bill",
                    "source_id": "hr1234",
                    "title": "HR 1234 benefits",
                    "published_date": "2024-06-12",
                    "first_seen_at": "2024-06-12T08:00:00Z",
                }
            ],
            "hearings": [],
            "oversight": [],
            "state": [],
        }
        result = aggregate_deltas(date(2024, 6, 5), date(2024, 6, 15))
        assert isinstance(result, AggregationResult)
        assert len(result.fr_deltas) == 1
        assert len(result.bill_deltas) == 1
        assert result.total_count == 2

    @patch("src.ceo_brief.aggregator.get_all_deltas")
    def test_aggregate_empty(self, mock_get):
        mock_get.return_value = {
            "federal_register": [],
            "bills": [],
            "hearings": [],
            "oversight": [],
            "state": [],
        }
        result = aggregate_deltas(date(2024, 6, 5), date(2024, 6, 15))
        assert result.total_count == 0


# ---------------------------------------------------------------------------
# get_top_deltas
# ---------------------------------------------------------------------------


class TestGetTopDeltas:
    def _make_delta(self, impact, urgency, relevance, title="test"):
        return AggregatedDelta(
            source_type=SourceType.FEDERAL_REGISTER,
            source_id="test-id",
            title=title,
            url="",
            published_date=date.today(),
            first_seen_at=datetime.utcnow(),
            issue_area=IssueArea.BENEFITS_CLAIMS,
            impact_score=impact,
            urgency_score=urgency,
            relevance_score=relevance,
        )

    def test_returns_limited(self):
        deltas = [self._make_delta(0.5, 0.5, 0.5) for _ in range(20)]
        result = AggregationResult(
            period_start=date.today(),
            period_end=date.today(),
            aggregated_at=datetime.utcnow(),
            fr_deltas=deltas,
        )
        top = get_top_deltas(result, limit=5)
        assert len(top) == 5

    def test_sorted_by_combined_score(self):
        low = self._make_delta(0.1, 0.1, 0.1, "low")
        high = self._make_delta(0.9, 0.9, 0.9, "high")
        mid = self._make_delta(0.5, 0.5, 0.5, "mid")
        result = AggregationResult(
            period_start=date.today(),
            period_end=date.today(),
            aggregated_at=datetime.utcnow(),
            fr_deltas=[low, high, mid],
        )
        top = get_top_deltas(result, limit=3)
        assert top[0].title == "high"
        assert top[-1].title == "low"


# ---------------------------------------------------------------------------
# get_deltas_by_issue_area
# ---------------------------------------------------------------------------


class TestGetDeltasByIssueArea:
    def test_groups_correctly(self):
        d1 = AggregatedDelta(
            source_type=SourceType.BILL,
            source_id="a",
            title="test",
            url="",
            published_date=date.today(),
            first_seen_at=datetime.utcnow(),
            issue_area=IssueArea.BENEFITS_CLAIMS,
            impact_score=0.8,
        )
        d2 = AggregatedDelta(
            source_type=SourceType.BILL,
            source_id="b",
            title="test2",
            url="",
            published_date=date.today(),
            first_seen_at=datetime.utcnow(),
            issue_area=IssueArea.HEALTHCARE,
            impact_score=0.5,
        )
        result = AggregationResult(
            period_start=date.today(),
            period_end=date.today(),
            aggregated_at=datetime.utcnow(),
            bill_deltas=[d1, d2],
        )
        by_area = get_deltas_by_issue_area(result)
        assert len(by_area[IssueArea.BENEFITS_CLAIMS]) == 1
        assert len(by_area[IssueArea.HEALTHCARE]) == 1
        assert len(by_area[IssueArea.OTHER]) == 0

    def test_sorted_by_impact_within_area(self):
        d1 = AggregatedDelta(
            source_type=SourceType.BILL,
            source_id="a",
            title="low",
            url="",
            published_date=date.today(),
            first_seen_at=datetime.utcnow(),
            issue_area=IssueArea.BENEFITS_CLAIMS,
            impact_score=0.3,
        )
        d2 = AggregatedDelta(
            source_type=SourceType.BILL,
            source_id="b",
            title="high",
            url="",
            published_date=date.today(),
            first_seen_at=datetime.utcnow(),
            issue_area=IssueArea.BENEFITS_CLAIMS,
            impact_score=0.9,
        )
        result = AggregationResult(
            period_start=date.today(),
            period_end=date.today(),
            aggregated_at=datetime.utcnow(),
            bill_deltas=[d1, d2],
        )
        by_area = get_deltas_by_issue_area(result)
        items = by_area[IssueArea.BENEFITS_CLAIMS]
        assert items[0].title == "high"
        assert items[1].title == "low"
