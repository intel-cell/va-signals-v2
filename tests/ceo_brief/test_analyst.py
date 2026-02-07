"""Tests for CEO Brief analyst — draft generation, citations, and analysis."""

from datetime import date, datetime

from src.ceo_brief.analyst import (
    _delta_to_citation,
    _draft_ask_from_delta,
    _draft_message_from_delta,
    _draft_risk_from_delta,
    _draft_snapshot_from_delta,
    _extract_topic,
    analyze_deltas,
)
from src.ceo_brief.schema import (
    AggregatedDelta,
    AggregationResult,
    AskItem,
    IssueArea,
    IssueSnapshot,
    Likelihood,
    RiskOpportunity,
    SourceCitation,
    SourceType,
)


def _make_delta(
    source_type=SourceType.FEDERAL_REGISTER,
    title="VA Final Rule on benefits",
    source_id="FR-001",
    issue_area=IssueArea.BENEFITS_CLAIMS,
    impact=0.7,
    urgency=0.5,
    relevance=1.0,
    summary="Test summary",
    metadata=None,
):
    return AggregatedDelta(
        source_type=source_type,
        source_id=source_id,
        title=title,
        url="https://example.com/doc",
        published_date=date.today(),
        first_seen_at=datetime.utcnow(),
        issue_area=issue_area,
        summary=summary,
        metadata=metadata or {},
        impact_score=impact,
        urgency_score=urgency,
        relevance_score=relevance,
    )


# ---------------------------------------------------------------------------
# _extract_topic
# ---------------------------------------------------------------------------


class TestExtractTopic:
    def test_removes_va_prefix(self):
        result = _extract_topic("Department of Veterans Affairs claims processing")
        assert not result.lower().startswith("department of veterans affairs")

    def test_removes_vba_prefix(self):
        result = _extract_topic("Veterans Benefits Administration rule change")
        assert not result.lower().startswith("veterans benefits administration")

    def test_truncates_long_titles(self):
        long_title = "A " * 100
        result = _extract_topic(long_title)
        assert len(result) <= 63  # 60 + potential "..."

    def test_short_title_preserved(self):
        result = _extract_topic("Short title here")
        assert result == "Short title here"


# ---------------------------------------------------------------------------
# _delta_to_citation
# ---------------------------------------------------------------------------


class TestDeltaToCitation:
    def test_creates_citation(self):
        delta = _make_delta()
        citation = _delta_to_citation(delta)
        assert isinstance(citation, SourceCitation)
        assert citation.source_type == SourceType.FEDERAL_REGISTER
        assert citation.source_id == "FR-001"
        assert citation.url == "https://example.com/doc"
        assert citation.date == date.today()

    def test_truncates_long_title(self):
        delta = _make_delta(title="x" * 200)
        citation = _delta_to_citation(delta)
        assert len(citation.title) <= 103  # 100 + "..."

    def test_excerpt_from_summary(self):
        delta = _make_delta(summary="A short summary for citation")
        citation = _delta_to_citation(delta)
        assert citation.excerpt == "A short summary for citation"


# ---------------------------------------------------------------------------
# _draft_message_from_delta
# ---------------------------------------------------------------------------


class TestDraftMessageFromDelta:
    def test_fr_final_rule_message(self):
        delta = _make_delta(
            source_type=SourceType.FEDERAL_REGISTER,
            title="VA Final Rule on disability ratings",
        )
        msg = _draft_message_from_delta(delta, 0)
        assert "finalized" in msg.text.lower()
        assert len(msg.supporting_citations) == 1

    def test_fr_proposed_rule_message(self):
        delta = _make_delta(
            source_type=SourceType.FEDERAL_REGISTER,
            title="VA Proposed Rule on accreditation",
        )
        msg = _draft_message_from_delta(delta, 0)
        assert "proposing" in msg.text.lower() or "comment" in msg.text.lower()

    def test_bill_passed_message(self):
        delta = _make_delta(
            source_type=SourceType.BILL,
            title="HR 1234 Veteran Benefits Act",
            metadata={"latest_action_text": "Passed House of Representatives"},
        )
        msg = _draft_message_from_delta(delta, 0)
        assert "passed" in msg.text.lower() or "congress" in msg.text.lower()

    def test_bill_hearing_message(self):
        delta = _make_delta(
            source_type=SourceType.BILL,
            title="HR 5678 Claims Improvement Act",
            metadata={"latest_action_text": "Hearing scheduled"},
        )
        msg = _draft_message_from_delta(delta, 0)
        assert "hearing" in msg.text.lower()

    def test_oversight_escalation_message(self):
        delta = _make_delta(
            source_type=SourceType.OVERSIGHT,
            title="OIG Report on claims processing",
            metadata={"is_escalation": True},
        )
        msg = _draft_message_from_delta(delta, 0)
        assert "oversight" in msg.text.lower() or "critical" in msg.text.lower()


# ---------------------------------------------------------------------------
# _draft_ask_from_delta
# ---------------------------------------------------------------------------


class TestDraftAskFromDelta:
    def test_fr_proposed_rule_returns_ask(self):
        delta = _make_delta(
            source_type=SourceType.FEDERAL_REGISTER,
            title="VA Proposed Rule on benefits",
        )
        ask = _draft_ask_from_delta(delta)
        assert isinstance(ask, AskItem)
        assert "comment" in ask.action.lower()

    def test_fr_final_rule_returns_ask(self):
        delta = _make_delta(
            source_type=SourceType.FEDERAL_REGISTER,
            title="VA Final Rule on processing",
        )
        ask = _draft_ask_from_delta(delta)
        assert isinstance(ask, AskItem)

    def test_bill_with_hearing_returns_ask(self):
        delta = _make_delta(
            source_type=SourceType.BILL,
            title="HR 1234",
            metadata={"latest_action_text": "Hearing scheduled", "committee_name": "HVAC"},
        )
        ask = _draft_ask_from_delta(delta)
        assert isinstance(ask, AskItem)
        assert ask.priority == Likelihood.HIGH

    def test_hearing_type_returns_ask(self):
        delta = _make_delta(
            source_type=SourceType.HEARING,
            title="Hearing on VA Claims",
            metadata={"committee_name": "Senate VA Committee", "hearing_date": "2024-07-01"},
        )
        ask = _draft_ask_from_delta(delta)
        assert isinstance(ask, AskItem)
        assert "testimony" in ask.action.lower() or "statement" in ask.action.lower()

    def test_news_returns_none(self):
        delta = _make_delta(source_type=SourceType.NEWS, title="News article")
        ask = _draft_ask_from_delta(delta)
        assert ask is None


# ---------------------------------------------------------------------------
# _draft_risk_from_delta
# ---------------------------------------------------------------------------


class TestDraftRiskFromDelta:
    def test_fr_final_rule_is_risk(self):
        delta = _make_delta(
            source_type=SourceType.FEDERAL_REGISTER,
            title="VA Final Rule on fee structure",
        )
        risk = _draft_risk_from_delta(delta)
        assert isinstance(risk, RiskOpportunity)
        assert risk.is_risk is True

    def test_fr_proposed_rule_is_opportunity(self):
        delta = _make_delta(
            source_type=SourceType.FEDERAL_REGISTER,
            title="VA Proposed Rule on benefits expansion",
        )
        risk = _draft_risk_from_delta(delta)
        assert isinstance(risk, RiskOpportunity)
        assert risk.is_risk is False

    def test_fr_notice_returns_none(self):
        delta = _make_delta(
            source_type=SourceType.FEDERAL_REGISTER,
            title="VA Notice of meeting",
        )
        risk = _draft_risk_from_delta(delta)
        assert risk is None

    def test_news_returns_none(self):
        delta = _make_delta(source_type=SourceType.NEWS, title="News article")
        risk = _draft_risk_from_delta(delta)
        assert risk is None

    def test_high_impact_sets_likelihood_high(self):
        delta = _make_delta(
            source_type=SourceType.FEDERAL_REGISTER,
            title="Final Rule",
            impact=0.8,
            relevance=0.9,
        )
        risk = _draft_risk_from_delta(delta)
        assert risk.likelihood == Likelihood.HIGH


# ---------------------------------------------------------------------------
# _draft_snapshot_from_delta
# ---------------------------------------------------------------------------


class TestDraftSnapshotFromDelta:
    def test_high_impact_creates_snapshot(self):
        delta = _make_delta(
            source_type=SourceType.FEDERAL_REGISTER,
            title="VA Proposed Rule on claims processing",
            impact=0.7,
        )
        snap = _draft_snapshot_from_delta(delta)
        assert isinstance(snap, IssueSnapshot)
        assert snap.issue_area == IssueArea.BENEFITS_CLAIMS

    def test_low_impact_returns_none(self):
        delta = _make_delta(impact=0.3)
        snap = _draft_snapshot_from_delta(delta)
        assert snap is None

    def test_bill_snapshot(self):
        delta = _make_delta(
            source_type=SourceType.BILL,
            title="HR 1234 Veterans Benefits Act",
            source_id="hr1234",
            impact=0.8,
            metadata={"latest_action_text": "Reported from committee"},
        )
        snap = _draft_snapshot_from_delta(delta)
        assert isinstance(snap, IssueSnapshot)
        assert "hr1234" in snap.policy_hook

    def test_news_returns_none(self):
        delta = _make_delta(source_type=SourceType.NEWS, impact=0.9)
        snap = _draft_snapshot_from_delta(delta)
        assert snap is None


# ---------------------------------------------------------------------------
# analyze_deltas
# ---------------------------------------------------------------------------


class TestAnalyzeDeltas:
    def _make_aggregation(self, n_fr=3, n_bills=2):
        fr = [
            _make_delta(
                source_type=SourceType.FEDERAL_REGISTER,
                title=f"VA Final Rule #{i}",
                source_id=f"FR-{i}",
                impact=0.9 - i * 0.1,
            )
            for i in range(n_fr)
        ]
        bills = [
            _make_delta(
                source_type=SourceType.BILL,
                title=f"HR {100 + i} Benefits Act",
                source_id=f"hr{100 + i}",
                impact=0.7 - i * 0.1,
                metadata={"latest_action_text": "Introduced"},
            )
            for i in range(n_bills)
        ]
        return AggregationResult(
            period_start=date.today(),
            period_end=date.today(),
            aggregated_at=datetime.utcnow(),
            fr_deltas=fr,
            bill_deltas=bills,
        )

    def test_returns_analysis_result(self):
        agg = self._make_aggregation()
        result = analyze_deltas(agg)
        assert result.total_deltas_reviewed == 5
        assert result.issues_identified <= 5

    def test_always_3_messages(self):
        agg = self._make_aggregation()
        result = analyze_deltas(agg)
        assert len(result.draft_messages) == 3

    def test_at_least_3_asks(self):
        agg = self._make_aggregation()
        result = analyze_deltas(agg)
        assert len(result.draft_asks) >= 3

    def test_at_least_3_objections(self):
        agg = self._make_aggregation()
        result = analyze_deltas(agg)
        assert len(result.draft_objections) >= 3

    def test_empty_aggregation(self):
        agg = AggregationResult(
            period_start=date.today(),
            period_end=date.today(),
            aggregated_at=datetime.utcnow(),
        )
        result = analyze_deltas(agg)
        assert len(result.draft_messages) == 3
        assert len(result.draft_objections) >= 3
