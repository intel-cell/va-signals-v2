"""Integration tests for the cross-source correlation engine.

Exercises CorrelationEngine.evaluate_rules() and engine.run() against
seeded test data to verify that correlation rules fire (or correctly
do not fire) under various conditions.
"""

from datetime import UTC, datetime, timedelta

from src.db import connect, execute
from src.signals.correlator import CorrelationEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _hours_ago(hours: int) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def _insert_om_event(
    event_id: str,
    title: str,
    *,
    event_type: str = "report",
    theme: str = "oversight",
    primary_source_type: str = "gao",
    pub_timestamp: str | None = None,
    summary: str = "",
    is_escalation: int = 0,
):
    now = _now_iso()
    pub = pub_timestamp or now
    con = connect()
    execute(
        con,
        """INSERT INTO om_events (
            event_id, event_type, theme, primary_source_type,
            primary_url, pub_timestamp, pub_precision, pub_source,
            title, summary, is_escalation, fetched_at, created_at, updated_at
        ) VALUES (
            :event_id, :event_type, :theme, :primary_source_type,
            :primary_url, :pub_timestamp, 'day', 'test',
            :title, :summary, :is_escalation, :fetched_at, :created_at, :updated_at
        )""",
        {
            "event_id": event_id,
            "event_type": event_type,
            "theme": theme,
            "primary_source_type": primary_source_type,
            "primary_url": f"https://example.com/{event_id}",
            "pub_timestamp": pub,
            "title": title,
            "summary": summary,
            "is_escalation": is_escalation,
            "fetched_at": now,
            "created_at": now,
            "updated_at": now,
        },
    )
    con.commit()
    con.close()


def _insert_bill(
    bill_id: str,
    title: str,
    *,
    policy_area: str = "",
    introduced_date: str | None = None,
):
    now = _now_iso()
    intro = introduced_date or now
    con = connect()
    execute(
        con,
        """INSERT INTO bills (
            bill_id, congress, bill_type, bill_number, title,
            policy_area, introduced_date, latest_action_date,
            first_seen_at, updated_at
        ) VALUES (
            :bill_id, 119, 'hr', 1, :title,
            :policy_area, :introduced_date, :introduced_date,
            :first_seen_at, :updated_at
        )""",
        {
            "bill_id": bill_id,
            "title": title,
            "policy_area": policy_area,
            "introduced_date": intro,
            "first_seen_at": now,
            "updated_at": now,
        },
    )
    con.commit()
    con.close()


def _insert_state_signal(
    signal_id: str,
    state: str,
    title: str,
    *,
    content: str = "",
    pub_date: str | None = None,
):
    now = _now_iso()
    pub = pub_date or now
    con = connect()
    execute(
        con,
        """INSERT INTO state_signals (
            signal_id, state, source_id, title, content, url, pub_date, fetched_at
        ) VALUES (
            :signal_id, :state, :source_id, :title, :content, :url, :pub_date, :fetched_at
        )""",
        {
            "signal_id": signal_id,
            "state": state,
            "source_id": f"src-{state.lower()}",
            "title": title,
            "content": content,
            "url": f"https://example.com/{signal_id}",
            "pub_date": pub,
            "fetched_at": now,
        },
    )
    con.commit()
    con.close()


def _seed_state_sources():
    """Seed the state_sources table so FK constraints are satisfied."""
    now = _now_iso()
    con = connect()
    for st in ("TX", "FL", "CA", "NY"):
        execute(
            con,
            """INSERT OR IGNORE INTO state_sources
               (source_id, state, source_type, name, url, created_at)
               VALUES (:sid, :state, 'news', :name, 'https://example.com', :created_at)""",
            {
                "sid": f"src-{st.lower()}",
                "state": st,
                "name": f"{st} VA News",
                "created_at": now,
            },
        )
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLegislativeToOversight:
    """legislative_to_oversight: bill + oversight within 336h window."""

    def test_detects_overlapping_disability_topics(self):
        _insert_om_event(
            "om-1",
            "Report on disability benefits backlog at VA",
            pub_timestamp=_hours_ago(100),
        )
        _insert_bill(
            "hr-1",
            "Veterans Disability Compensation Improvement Act",
            policy_area="disability",
            introduced_date=_hours_ago(50),
        )

        engine = CorrelationEngine()
        signals = engine.evaluate_rules()

        leg_signals = [s for s in signals if s.rule_id == "legislative_to_oversight"]
        assert len(leg_signals) >= 1, (
            f"Expected at least 1 legislative_to_oversight signal, got {len(leg_signals)}"
        )
        assert "disability_benefits" in leg_signals[0].topics

    def test_no_correlation_when_topics_dont_overlap(self):
        _insert_om_event(
            "om-weather",
            "National Weather Service update for coastal areas",
            pub_timestamp=_hours_ago(50),
        )
        _insert_bill(
            "hr-agri",
            "Agricultural Subsidy Reform Act of 2026",
            policy_area="agriculture",
            introduced_date=_hours_ago(50),
        )

        engine = CorrelationEngine()
        signals = engine.evaluate_rules()

        leg_signals = [s for s in signals if s.rule_id == "legislative_to_oversight"]
        assert len(leg_signals) == 0, (
            f"Expected no correlation for unrelated topics, got {len(leg_signals)}"
        )


class TestStateDivergence:
    """state_divergence: 3+ states with same topic within 168h window."""

    def test_detects_three_states_same_topic(self):
        _seed_state_sources()
        recent = _hours_ago(24)
        _insert_state_signal(
            "ss-tx", "TX", "Claims processing backlog grows in Texas", pub_date=recent
        )
        _insert_state_signal("ss-fl", "FL", "Florida VA backlog at record levels", pub_date=recent)
        _insert_state_signal(
            "ss-ca", "CA", "California veterans face claims processing delays", pub_date=recent
        )

        engine = CorrelationEngine()
        signals = engine.evaluate_rules()

        div_signals = [s for s in signals if s.rule_id == "state_divergence"]
        assert len(div_signals) >= 1, (
            f"Expected at least 1 state_divergence signal, got {len(div_signals)}"
        )
        assert "claims_backlog" in div_signals[0].topics


class TestFullPipeline:
    """engine.run() stores compound signals to the database."""

    def test_run_stores_to_compound_signals_table(self):
        _insert_om_event(
            "om-pipe-1",
            "GAO report on veteran benefits compensation delays",
            pub_timestamp=_hours_ago(100),
        )
        _insert_bill(
            "hr-pipe-1",
            "Veteran Benefits Compensation Reform Act",
            policy_area="compensation",
            introduced_date=_hours_ago(50),
        )

        engine = CorrelationEngine()
        result = engine.run()

        assert result["total_signals"] >= 1
        assert result["stored"] >= 1

        # Verify directly in DB
        con = connect()
        cur = execute(
            con,
            "SELECT compound_id, rule_id, topics FROM compound_signals WHERE rule_id = :rule_id",
            {"rule_id": "legislative_to_oversight"},
        )
        rows = cur.fetchall()
        con.close()

        assert len(rows) >= 1, "Expected at least 1 compound_signal stored in DB"


class TestTitleSimilarity:
    """_title_similarity threshold behavior."""

    def test_high_similarity_similar_titles(self):
        engine = CorrelationEngine()
        sim = engine._title_similarity(
            ["Veteran disability benefits compensation reform"],
            ["Veteran disability benefits compensation improvement"],
        )
        assert sim > 0.5, f"Expected high similarity for near-identical titles, got {sim}"

    def test_low_similarity_unrelated_titles(self):
        engine = CorrelationEngine()
        sim = engine._title_similarity(
            ["National weather forecast for coastal regions"],
            ["Agricultural trade policy reform legislation"],
        )
        assert sim < 0.3, f"Expected low similarity for unrelated titles, got {sim}"
