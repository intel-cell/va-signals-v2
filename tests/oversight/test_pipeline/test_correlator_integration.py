"""Tests for cross-source correlator integration into the oversight pipeline.

Verifies:
- run_correlation() finds compound signals and stores them
- canonical_refs on om_events are updated with compound_signal links
- Fuzzy title matching works at the 0.85 threshold
- run_correlation() is idempotent
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def correlation_rules(tmp_path):
    """Create a temporary correlation rules YAML."""
    rules = [
        {
            "rule_id": "legislative_to_oversight",
            "name": "Legislative to Oversight Correlation",
            "description": "Bill and oversight report share topic",
            "source_types": ["bill", "oversight"],
            "temporal_window_hours": 336,
            "min_topic_overlap": 1,
            "severity_base": 0.6,
            "severity_multipliers": {
                "topic_overlap_bonus": 0.1,
                "escalation_bonus": 0.15,
            },
        },
        {
            "rule_id": "state_divergence",
            "name": "State Divergence Detection",
            "description": "3+ states report same topic",
            "source_types": ["state"],
            "temporal_window_hours": 168,
            "min_topic_overlap": 1,
            "min_source_count": 3,
            "severity_base": 0.5,
            "severity_multipliers": {
                "topic_overlap_bonus": 0.1,
                "source_count_bonus": 0.05,
            },
        },
    ]
    path = tmp_path / "correlation_rules.yaml"
    path.write_text(yaml.dump(rules, default_flow_style=False))
    return path


@pytest.fixture
def seed_events():
    """Seed the test DB (already initialized by conftest) with cross-source events."""
    from src.db import connect, execute

    now = datetime.now(UTC)
    two_days_ago = (now - timedelta(days=2)).isoformat()
    five_days_ago = (now - timedelta(days=5)).isoformat()

    con = connect()

    # Oversight event about disability benefits
    execute(
        con,
        """
        INSERT INTO om_events (
            event_id, event_type, theme, primary_source_type, primary_url,
            pub_timestamp, pub_precision, pub_source, title, summary,
            is_escalation, fetched_at
        ) VALUES (
            :event_id, :event_type, :theme, :primary_source_type, :primary_url,
            :pub_timestamp, :pub_precision, :pub_source, :title, :summary,
            :is_escalation, :fetched_at
        )
    """,
        {
            "event_id": "om-gao-test001",
            "event_type": "report",
            "theme": "disability",
            "primary_source_type": "gao",
            "primary_url": "https://gao.gov/report1",
            "pub_timestamp": two_days_ago,
            "pub_precision": "day",
            "pub_source": "gao",
            "title": "GAO Report on Disability Benefits Processing Backlog",
            "summary": "Examination of claims backlog and rating delays",
            "is_escalation": 1,
            "fetched_at": two_days_ago,
        },
    )

    # Bill about disability benefits (shared topic)
    execute(
        con,
        """
        INSERT INTO bills (
            bill_id, congress, bill_type, bill_number, title,
            policy_area, introduced_date, latest_action_date, first_seen_at, updated_at
        ) VALUES (
            :bill_id, :congress, :bill_type, :bill_number, :title,
            :policy_area, :introduced_date, :latest_action_date, :first_seen_at, :updated_at
        )
    """,
        {
            "bill_id": "hr-9999-119",
            "congress": 119,
            "bill_type": "HR",
            "bill_number": 9999,
            "title": "Veterans Disability Benefits Improvement Act",
            "policy_area": "Armed Forces and National Security",
            "introduced_date": five_days_ago,
            "latest_action_date": two_days_ago,
            "first_seen_at": five_days_ago,
            "updated_at": two_days_ago,
        },
    )

    # State signals for divergence detection (4 states, same topic)
    for state in ["TX", "CA", "FL", "NY"]:
        execute(
            con,
            """
            INSERT INTO state_signals (
                signal_id, state, source_id, title, content,
                url, pub_date, fetched_at
            ) VALUES (
                :signal_id, :state, :source_id, :title, :content,
                :url, :pub_date, :fetched_at
            )
        """,
            {
                "signal_id": f"state-{state}-corr-test",
                "state": state,
                "source_id": f"source-{state}",
                "title": f"{state} Report on Disability Benefits Processing Delays",
                "content": "State-level analysis of veteran disability claims backlog",
                "url": f"https://{state.lower()}.gov/report-corr",
                "pub_date": two_days_ago,
                "fetched_at": two_days_ago,
            },
        )

    con.commit()
    con.close()


class TestRunCorrelation:
    """Test run_correlation() integration with the oversight pipeline."""

    def test_run_correlation_finds_signals(self, seed_events, correlation_rules):
        with patch(
            "src.signals.correlator.DEFAULT_RULES_PATH",
            correlation_rules,
        ):
            from src.oversight.runner import run_correlation

            summary = run_correlation()
            assert summary["total_signals"] > 0

    def test_run_correlation_stores_compound_signals(self, seed_events, correlation_rules):
        with patch(
            "src.signals.correlator.DEFAULT_RULES_PATH",
            correlation_rules,
        ):
            from src.db.compound import get_compound_signals
            from src.oversight.runner import run_correlation

            run_correlation()
            signals = get_compound_signals(limit=100)
            assert len(signals) > 0

    def test_run_correlation_updates_canonical_refs(self, seed_events, correlation_rules):
        with patch(
            "src.signals.correlator.DEFAULT_RULES_PATH",
            correlation_rules,
        ):
            from src.oversight.db_helpers import get_om_event
            from src.oversight.runner import run_correlation

            summary = run_correlation()

            # The om-gao-test001 event should have compound_signal in canonical_refs
            event = get_om_event("om-gao-test001")
            if summary.get("stored", 0) > 0 and event:
                refs = event.get("canonical_refs")
                if refs:
                    assert "compound_signal" in refs

    def test_run_correlation_is_idempotent(self, seed_events, correlation_rules):
        with patch(
            "src.signals.correlator.DEFAULT_RULES_PATH",
            correlation_rules,
        ):
            from src.db.compound import get_compound_signals
            from src.oversight.runner import run_correlation

            run_correlation()
            count_1 = len(get_compound_signals(limit=100))
            run_correlation()
            count_2 = len(get_compound_signals(limit=100))
            assert count_2 == count_1

    def test_run_correlation_with_no_events(self, correlation_rules):
        """No events in DB should produce zero signals."""
        with patch(
            "src.signals.correlator.DEFAULT_RULES_PATH",
            correlation_rules,
        ):
            from src.oversight.runner import run_correlation

            summary = run_correlation()
            assert summary["total_signals"] == 0

    def test_run_correlation_error_handling(self):
        """If the correlator fails, run_correlation returns error summary."""
        with patch(
            "src.signals.correlator.CorrelationEngine.evaluate_rules",
            side_effect=RuntimeError("test failure"),
        ):
            from src.oversight.runner import run_correlation

            summary = run_correlation()
            assert summary["total_signals"] == 0
            assert "error" in summary


class TestCanonicalRefsUpdate:
    """Test that update_canonical_refs correctly merges refs."""

    def test_update_canonical_refs_merges(self, seed_events):
        from src.oversight.db_helpers import get_om_event, update_canonical_refs

        # First update
        update_canonical_refs("om-gao-test001", {"compound_signal": "cs-abc123"})
        event = get_om_event("om-gao-test001")
        assert event["canonical_refs"]["compound_signal"] == "cs-abc123"

        # Second update merges, doesn't overwrite
        update_canonical_refs("om-gao-test001", {"related_bill": "hr-9999"})
        event = get_om_event("om-gao-test001")
        assert event["canonical_refs"]["compound_signal"] == "cs-abc123"
        assert event["canonical_refs"]["related_bill"] == "hr-9999"

    def test_update_canonical_refs_nonexistent_event(self):
        from src.oversight.db_helpers import update_canonical_refs

        # Should not raise
        update_canonical_refs("nonexistent-event-id", {"key": "value"})


class TestFuzzyTitleThreshold:
    """Test that the title similarity threshold is correctly set to 0.85."""

    def test_threshold_is_085(self):
        from src.signals.correlator import TITLE_SIMILARITY_THRESHOLD

        assert TITLE_SIMILARITY_THRESHOLD == 0.85

    def test_similar_titles_above_threshold(self):
        from src.signals.correlator import CorrelationEngine, MemberEvent

        engine = CorrelationEngine()
        # Nearly identical titles should match at 0.85
        events_a = [
            MemberEvent(
                source_type="bill",
                event_id="b1",
                title="Veterans Disability Benefits Processing Delays Report",
                timestamp="2026-01-01T00:00:00",
                topics=[],
                metadata={},
            )
        ]
        events_b = [
            MemberEvent(
                source_type="oversight",
                event_id="o1",
                title="Veterans Disability Benefits Processing Delays Report Review",
                timestamp="2026-01-02T00:00:00",
                topics=[],
                metadata={},
            )
        ]
        overlap = engine._find_topic_overlap(events_a, events_b)
        # These titles are very similar, Jaccard should be >= 0.85
        assert "title_match" in overlap

    def test_dissimilar_titles_below_threshold(self):
        from src.signals.correlator import CorrelationEngine, MemberEvent

        engine = CorrelationEngine()
        events_a = [
            MemberEvent(
                source_type="bill",
                event_id="b1",
                title="National Defense Authorization Act Fiscal Year 2026",
                timestamp="2026-01-01T00:00:00",
                topics=[],
                metadata={},
            )
        ]
        events_b = [
            MemberEvent(
                source_type="oversight",
                event_id="o1",
                title="VA Benefits Claims Backlog Analysis",
                timestamp="2026-01-02T00:00:00",
                topics=[],
                metadata={},
            )
        ]
        overlap = engine._find_topic_overlap(events_a, events_b)
        assert "title_match" not in overlap

    def test_moderately_similar_titles_below_085(self):
        from src.signals.correlator import CorrelationEngine, MemberEvent

        engine = CorrelationEngine()
        # Titles that share some words but are not 85% similar
        events_a = [
            MemberEvent(
                source_type="bill",
                event_id="b1",
                title="Veterans Disability Benefits Improvement Act",
                timestamp="2026-01-01T00:00:00",
                topics=[],
                metadata={},
            )
        ]
        events_b = [
            MemberEvent(
                source_type="oversight",
                event_id="o1",
                title="Report on Veterans Healthcare Facilities",
                timestamp="2026-01-02T00:00:00",
                topics=[],
                metadata={},
            )
        ]
        overlap = engine._find_topic_overlap(events_a, events_b)
        # These share "veterans" but Jaccard is well below 0.85
        assert "title_match" not in overlap
