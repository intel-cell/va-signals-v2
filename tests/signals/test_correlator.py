"""Tests for the cross-source correlation engine.

TDD: Tests written first, implementation follows.
"""

import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite database with schema."""
    db_path = tmp_path / "test_signals.db"
    con = sqlite3.connect(str(db_path), timeout=30)
    con.execute("PRAGMA journal_mode=WAL")

    # Create minimal tables needed for correlation
    con.executescript("""
        CREATE TABLE IF NOT EXISTS om_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            theme TEXT,
            primary_source_type TEXT NOT NULL,
            primary_url TEXT NOT NULL,
            pub_timestamp TEXT,
            pub_precision TEXT NOT NULL,
            pub_source TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            is_escalation INTEGER DEFAULT 0,
            fetched_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS bills (
            bill_id TEXT PRIMARY KEY,
            congress INTEGER NOT NULL,
            bill_type TEXT NOT NULL,
            bill_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            policy_area TEXT,
            introduced_date TEXT,
            latest_action_date TEXT,
            latest_action_text TEXT,
            first_seen_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS hearings (
            event_id TEXT PRIMARY KEY,
            congress INTEGER NOT NULL,
            chamber TEXT NOT NULL,
            committee_code TEXT NOT NULL,
            committee_name TEXT,
            hearing_date TEXT NOT NULL,
            title TEXT,
            status TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fr_seen (
            doc_id TEXT PRIMARY KEY,
            published_date TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            source_url TEXT NOT NULL,
            document_type TEXT,
            title TEXT
        );

        CREATE TABLE IF NOT EXISTS state_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT UNIQUE NOT NULL,
            state TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            url TEXT NOT NULL,
            pub_date TEXT,
            fetched_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS compound_signals (
            compound_id TEXT PRIMARY KEY,
            rule_id TEXT NOT NULL,
            severity_score REAL NOT NULL,
            narrative TEXT,
            temporal_window_hours INTEGER,
            member_events TEXT NOT NULL,
            topics TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            resolved_at TEXT,
            UNIQUE(rule_id, compound_id)
        );
        CREATE INDEX IF NOT EXISTS idx_compound_signals_rule ON compound_signals(rule_id);
        CREATE INDEX IF NOT EXISTS idx_compound_signals_created ON compound_signals(created_at);
        CREATE INDEX IF NOT EXISTS idx_compound_signals_severity ON compound_signals(severity_score);
    """)
    con.commit()
    con.close()

    with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
        with patch("src.db.core.DB_PATH", db_path):
            yield db_path


@pytest.fixture
def rules_path(tmp_path):
    """Create a temporary rules YAML file."""
    rules = [
        {
            "rule_id": "legislative_to_oversight",
            "name": "Legislative to Oversight Correlation",
            "description": "Bill introduced and related oversight report within temporal window",
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
            "description": "3+ states report same topic within temporal window",
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
        {
            "rule_id": "oversight_escalation",
            "name": "Oversight Escalation Correlation",
            "description": "Hearing scheduled and related oversight report within temporal window",
            "source_types": ["hearing", "oversight"],
            "temporal_window_hours": 504,
            "min_topic_overlap": 1,
            "severity_base": 0.7,
            "severity_multipliers": {
                "topic_overlap_bonus": 0.1,
                "escalation_bonus": 0.2,
            },
        },
        {
            "rule_id": "regulatory_federal_register",
            "name": "Regulatory Federal Register Correlation",
            "description": "FR rule published and related bill/hearing within temporal window",
            "source_types": ["federal_register", "bill", "hearing"],
            "temporal_window_hours": 720,
            "min_topic_overlap": 1,
            "severity_base": 0.55,
            "severity_multipliers": {
                "topic_overlap_bonus": 0.1,
            },
        },
    ]
    path = tmp_path / "correlation_rules.yaml"
    path.write_text(yaml.dump(rules, default_flow_style=False))
    return path


@pytest.fixture
def populated_db(tmp_db):
    """Populate the test DB with events across sources for correlation testing."""
    con = sqlite3.connect(str(tmp_db), timeout=30)
    now = datetime.now(timezone.utc)
    two_days_ago = (now - timedelta(days=2)).isoformat()
    five_days_ago = (now - timedelta(days=5)).isoformat()
    one_day_ago = (now - timedelta(days=1)).isoformat()

    # Insert oversight event about disability benefits
    con.execute("""
        INSERT INTO om_events (event_id, event_type, theme, primary_source_type,
            primary_url, pub_timestamp, pub_precision, pub_source, title, summary,
            is_escalation, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "om-001", "report", "disability", "gao",
        "https://gao.gov/report1", two_days_ago, "day", "gao",
        "GAO Report on Disability Benefits Processing Backlog",
        "Examination of claims backlog and rating delays",
        1, two_days_ago,
    ))

    con.execute("""
        INSERT INTO om_events (event_id, event_type, theme, primary_source_type,
            primary_url, pub_timestamp, pub_precision, pub_source, title, summary,
            is_escalation, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "om-002", "report", "appeals", "oig",
        "https://oig.va.gov/report2", one_day_ago, "day", "oig",
        "OIG Review of Appeals Processing",
        "Review of BVA appeal processing timelines",
        0, one_day_ago,
    ))

    # Insert bill about disability benefits
    con.execute("""
        INSERT INTO bills (bill_id, congress, bill_type, bill_number, title,
            policy_area, introduced_date, latest_action_date, first_seen_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "hr-1234-119", 119, "HR", 1234,
        "Veterans Disability Benefits Improvement Act",
        "Armed Forces and National Security",
        five_days_ago, two_days_ago, five_days_ago, two_days_ago,
    ))

    # Insert hearing about disability
    con.execute("""
        INSERT INTO hearings (event_id, congress, chamber, committee_code,
            committee_name, hearing_date, title, status, first_seen_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "hearing-001", 119, "House", "HVAC",
        "House Veterans Affairs Committee",
        one_day_ago, "Hearing on Disability Claims Backlog",
        "scheduled", five_days_ago, one_day_ago,
    ))

    # Insert FR document about disability rating
    con.execute("""
        INSERT INTO fr_seen (doc_id, published_date, first_seen_at, source_url,
            document_type, title)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "fr-2026-01234", two_days_ago, two_days_ago,
        "https://federalregister.gov/d/2026-01234",
        "Rule", "Schedule for Rating Disabilities Update",
    ))

    # Insert state signals (3 states, same topic)
    for i, state in enumerate(["TX", "CA", "FL", "NY"]):
        con.execute("""
            INSERT INTO state_signals (signal_id, state, source_id, title, content,
                url, pub_date, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"state-{state}-001", state, f"source-{state}",
            f"{state} Report on Disability Benefits Processing Delays",
            "State-level analysis of veteran disability claims backlog",
            f"https://{state.lower()}.gov/report1",
            two_days_ago, two_days_ago,
        ))

    con.commit()
    con.close()
    return tmp_db


# ===========================================================================
# Tests: Rule Loading
# ===========================================================================


class TestRuleLoading:
    """Test that rules are loaded and validated from YAML."""

    def test_load_rules_from_yaml(self, rules_path, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine(rules_path=rules_path)
            assert len(engine.rules) == 4

    def test_rule_has_required_fields(self, rules_path, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine(rules_path=rules_path)
            rule = engine.rules[0]
            assert rule.rule_id == "legislative_to_oversight"
            assert rule.name == "Legislative to Oversight Correlation"
            assert rule.source_types == ["bill", "oversight"]
            assert rule.temporal_window_hours == 336
            assert rule.min_topic_overlap == 1
            assert rule.severity_base == 0.6

    def test_load_default_rules(self, tmp_db):
        """Loading without explicit path uses config/correlation_rules.yaml."""
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine()
            # Should load rules from default path (may be 0 if file doesn't exist yet)
            assert isinstance(engine.rules, list)

    def test_load_rules_missing_file_returns_empty(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine(rules_path=Path("/nonexistent/rules.yaml"))
            assert engine.rules == []

    def test_rule_ids_are_unique(self, rules_path, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine(rules_path=rules_path)
            ids = [r.rule_id for r in engine.rules]
            assert len(ids) == len(set(ids))


# ===========================================================================
# Tests: Topic Overlap
# ===========================================================================


class TestTopicOverlap:
    """Test topic matching between events from different sources."""

    def test_find_overlap_with_shared_topics(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine, MemberEvent
            engine = CorrelationEngine()
            events_a = [MemberEvent(
                source_type="bill", event_id="b1", title="Disability Benefits Act",
                timestamp="2026-01-01T00:00:00", topics=["disability_benefits", "rating"],
                metadata={},
            )]
            events_b = [MemberEvent(
                source_type="oversight", event_id="o1", title="GAO Disability Report",
                timestamp="2026-01-02T00:00:00", topics=["disability_benefits", "claims_backlog"],
                metadata={},
            )]
            overlap = engine._find_topic_overlap(events_a, events_b)
            assert "disability_benefits" in overlap

    def test_find_overlap_no_shared_topics(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine, MemberEvent
            engine = CorrelationEngine()
            events_a = [MemberEvent(
                source_type="bill", event_id="b1", title="Tax Reform",
                timestamp="2026-01-01T00:00:00", topics=["taxation"],
                metadata={},
            )]
            events_b = [MemberEvent(
                source_type="oversight", event_id="o1", title="Healthcare Report",
                timestamp="2026-01-02T00:00:00", topics=["healthcare"],
                metadata={},
            )]
            overlap = engine._find_topic_overlap(events_a, events_b)
            assert overlap == []

    def test_title_similarity_adds_overlap(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine, MemberEvent
            engine = CorrelationEngine()
            events_a = [MemberEvent(
                source_type="bill", event_id="b1",
                title="Veterans Disability Benefits Improvement",
                timestamp="2026-01-01T00:00:00", topics=[],
                metadata={},
            )]
            events_b = [MemberEvent(
                source_type="oversight", event_id="o1",
                title="Report on Veterans Disability Benefits",
                timestamp="2026-01-02T00:00:00", topics=[],
                metadata={},
            )]
            overlap = engine._find_topic_overlap(events_a, events_b)
            # Title similarity should produce a "title_match" topic
            assert "title_match" in overlap

    def test_title_similarity_below_threshold(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine, MemberEvent
            engine = CorrelationEngine()
            events_a = [MemberEvent(
                source_type="bill", event_id="b1",
                title="National Defense Authorization Act",
                timestamp="2026-01-01T00:00:00", topics=[],
                metadata={},
            )]
            events_b = [MemberEvent(
                source_type="oversight", event_id="o1",
                title="Report on Veteran Benefits",
                timestamp="2026-01-02T00:00:00", topics=[],
                metadata={},
            )]
            overlap = engine._find_topic_overlap(events_a, events_b)
            assert "title_match" not in overlap

    def test_multiple_events_aggregate_topics(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine, MemberEvent
            engine = CorrelationEngine()
            events_a = [
                MemberEvent(source_type="bill", event_id="b1", title="Bill A",
                            timestamp="2026-01-01T00:00:00", topics=["disability_benefits"], metadata={}),
                MemberEvent(source_type="bill", event_id="b2", title="Bill B",
                            timestamp="2026-01-01T00:00:00", topics=["appeals"], metadata={}),
            ]
            events_b = [
                MemberEvent(source_type="oversight", event_id="o1", title="Report",
                            timestamp="2026-01-02T00:00:00", topics=["appeals", "rating"], metadata={}),
            ]
            overlap = engine._find_topic_overlap(events_a, events_b)
            assert "appeals" in overlap


# ===========================================================================
# Tests: Severity Computation
# ===========================================================================


class TestSeverityComputation:
    """Test severity score calculation."""

    def test_base_severity(self, rules_path, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine, MemberEvent
            engine = CorrelationEngine(rules_path=rules_path)
            rule = engine.rules[0]  # legislative_to_oversight, base=0.6
            events = [
                MemberEvent(source_type="bill", event_id="b1", title="Bill",
                            timestamp="2026-01-01", topics=["disability_benefits"], metadata={}),
                MemberEvent(source_type="oversight", event_id="o1", title="Report",
                            timestamp="2026-01-02", topics=["disability_benefits"], metadata={}),
            ]
            score = engine._compute_severity(rule, events, ["disability_benefits"])
            assert score >= rule.severity_base
            assert score <= 1.0

    def test_topic_overlap_bonus(self, rules_path, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine, MemberEvent
            engine = CorrelationEngine(rules_path=rules_path)
            rule = engine.rules[0]
            events = [
                MemberEvent(source_type="bill", event_id="b1", title="Bill",
                            timestamp="2026-01-01", topics=["disability_benefits", "rating"], metadata={}),
                MemberEvent(source_type="oversight", event_id="o1", title="Report",
                            timestamp="2026-01-02", topics=["disability_benefits", "rating"], metadata={}),
            ]
            # More topic overlap = higher score
            score_two = engine._compute_severity(rule, events, ["disability_benefits", "rating"])
            score_one = engine._compute_severity(rule, events, ["disability_benefits"])
            assert score_two > score_one

    def test_severity_capped_at_1(self, rules_path, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine, MemberEvent
            engine = CorrelationEngine(rules_path=rules_path)
            rule = engine.rules[0]
            events = [
                MemberEvent(source_type="bill", event_id="b1", title="Bill",
                            timestamp="2026-01-01", topics=["a", "b", "c", "d", "e"], metadata={"is_escalation": True}),
                MemberEvent(source_type="oversight", event_id="o1", title="Report",
                            timestamp="2026-01-02", topics=["a", "b", "c", "d", "e"], metadata={"is_escalation": True}),
            ]
            score = engine._compute_severity(rule, events, ["a", "b", "c", "d", "e"])
            assert score <= 1.0

    def test_escalation_bonus(self, rules_path, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine, MemberEvent
            engine = CorrelationEngine(rules_path=rules_path)
            rule = engine.rules[0]  # has escalation_bonus: 0.15
            events_no_esc = [
                MemberEvent(source_type="bill", event_id="b1", title="Bill",
                            timestamp="2026-01-01", topics=["disability_benefits"], metadata={}),
                MemberEvent(source_type="oversight", event_id="o1", title="Report",
                            timestamp="2026-01-02", topics=["disability_benefits"], metadata={}),
            ]
            events_esc = [
                MemberEvent(source_type="bill", event_id="b1", title="Bill",
                            timestamp="2026-01-01", topics=["disability_benefits"], metadata={}),
                MemberEvent(source_type="oversight", event_id="o1", title="Report",
                            timestamp="2026-01-02", topics=["disability_benefits"],
                            metadata={"is_escalation": True}),
            ]
            score_no = engine._compute_severity(rule, events_no_esc, ["disability_benefits"])
            score_esc = engine._compute_severity(rule, events_esc, ["disability_benefits"])
            assert score_esc > score_no


# ===========================================================================
# Tests: Narrative Generation
# ===========================================================================


class TestNarrativeGeneration:
    """Test human-readable narrative generation."""

    def test_narrative_includes_rule_name(self, rules_path, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine, MemberEvent
            engine = CorrelationEngine(rules_path=rules_path)
            rule = engine.rules[0]
            events = [
                MemberEvent(source_type="bill", event_id="b1",
                            title="Veterans Disability Benefits Improvement Act",
                            timestamp="2026-01-01", topics=["disability_benefits"], metadata={}),
                MemberEvent(source_type="oversight", event_id="o1",
                            title="GAO Report on Disability Benefits",
                            timestamp="2026-01-02", topics=["disability_benefits"], metadata={}),
            ]
            narrative = engine._generate_narrative(rule, events, ["disability_benefits"])
            assert "Legislative to Oversight" in narrative

    def test_narrative_includes_topics(self, rules_path, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine, MemberEvent
            engine = CorrelationEngine(rules_path=rules_path)
            rule = engine.rules[0]
            events = [
                MemberEvent(source_type="bill", event_id="b1", title="Bill",
                            timestamp="2026-01-01", topics=["disability_benefits"], metadata={}),
                MemberEvent(source_type="oversight", event_id="o1", title="Report",
                            timestamp="2026-01-02", topics=["disability_benefits"], metadata={}),
            ]
            narrative = engine._generate_narrative(rule, events, ["disability_benefits"])
            assert "disability_benefits" in narrative

    def test_narrative_includes_source_count(self, rules_path, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine, MemberEvent
            engine = CorrelationEngine(rules_path=rules_path)
            rule = engine.rules[0]
            events = [
                MemberEvent(source_type="bill", event_id="b1", title="Bill A",
                            timestamp="2026-01-01", topics=["disability_benefits"], metadata={}),
                MemberEvent(source_type="oversight", event_id="o1", title="Report A",
                            timestamp="2026-01-02", topics=["disability_benefits"], metadata={}),
            ]
            narrative = engine._generate_narrative(rule, events, ["disability_benefits"])
            assert "2" in narrative  # 2 events

    def test_narrative_returns_string(self, rules_path, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine, MemberEvent
            engine = CorrelationEngine(rules_path=rules_path)
            rule = engine.rules[0]
            events = [
                MemberEvent(source_type="bill", event_id="b1", title="Bill",
                            timestamp="2026-01-01", topics=[], metadata={}),
            ]
            narrative = engine._generate_narrative(rule, events, [])
            assert isinstance(narrative, str)
            assert len(narrative) > 0


# ===========================================================================
# Tests: Event Fetching
# ===========================================================================


class TestEventFetching:
    """Test fetching recent events from all source tables."""

    def test_fetch_oversight_events(self, populated_db):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine()
            events = engine._fetch_recent_events(hours=168)
            assert "oversight" in events
            assert len(events["oversight"]) >= 1

    def test_fetch_bill_events(self, populated_db):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine()
            events = engine._fetch_recent_events(hours=168)
            assert "bill" in events
            assert len(events["bill"]) >= 1

    def test_fetch_hearing_events(self, populated_db):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine()
            events = engine._fetch_recent_events(hours=168)
            assert "hearing" in events
            assert len(events["hearing"]) >= 1

    def test_fetch_federal_register_events(self, populated_db):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine()
            events = engine._fetch_recent_events(hours=168)
            assert "federal_register" in events
            assert len(events["federal_register"]) >= 1

    def test_fetch_state_events(self, populated_db):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine()
            events = engine._fetch_recent_events(hours=168)
            assert "state" in events
            assert len(events["state"]) >= 3

    def test_fetch_respects_time_window(self, populated_db):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine()
            # Very short window should get fewer events
            events_short = engine._fetch_recent_events(hours=1)
            events_long = engine._fetch_recent_events(hours=720)
            total_short = sum(len(v) for v in events_short.values())
            total_long = sum(len(v) for v in events_long.values())
            assert total_long >= total_short

    def test_member_event_has_topics(self, populated_db):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine()
            events = engine._fetch_recent_events(hours=168)
            # Oversight event about disability should have topics extracted
            for ev in events.get("oversight", []):
                if "disability" in ev.title.lower() or "backlog" in ev.title.lower():
                    assert len(ev.topics) > 0
                    break


# ===========================================================================
# Tests: Full Engine Evaluation
# ===========================================================================


class TestEngineEvaluation:
    """Test full rule evaluation pipeline."""

    def test_evaluate_returns_compound_signals(self, populated_db, rules_path):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine(rules_path=rules_path)
            signals = engine.evaluate_rules()
            assert isinstance(signals, list)

    def test_legislative_to_oversight_detected(self, populated_db, rules_path):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine(rules_path=rules_path)
            signals = engine.evaluate_rules()
            rule_ids = [s.rule_id for s in signals]
            assert "legislative_to_oversight" in rule_ids

    def test_state_divergence_detected(self, populated_db, rules_path):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine(rules_path=rules_path)
            signals = engine.evaluate_rules()
            rule_ids = [s.rule_id for s in signals]
            assert "state_divergence" in rule_ids

    def test_compound_signal_has_required_fields(self, populated_db, rules_path):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine(rules_path=rules_path)
            signals = engine.evaluate_rules()
            assert len(signals) > 0
            sig = signals[0]
            assert sig.compound_id
            assert sig.rule_id
            assert 0 < sig.severity_score <= 1.0
            assert sig.narrative
            assert sig.temporal_window_hours > 0
            assert len(sig.member_events) >= 2 or sig.rule_id == "state_divergence"
            assert isinstance(sig.topics, list)
            assert sig.created_at

    def test_no_duplicate_compound_ids(self, populated_db, rules_path):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine(rules_path=rules_path)
            signals = engine.evaluate_rules()
            ids = [s.compound_id for s in signals]
            assert len(ids) == len(set(ids))

    def test_run_returns_summary_dict(self, populated_db, rules_path):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine(rules_path=rules_path)
            summary = engine.run()
            assert isinstance(summary, dict)
            assert "total_signals" in summary
            assert "by_rule" in summary
            assert summary["total_signals"] >= 0


# ===========================================================================
# Tests: DB CRUD (compound.py)
# ===========================================================================


class TestCompoundDB:
    """Test database CRUD operations for compound_signals table."""

    def _make_signal_data(self, rule_id="test_rule", severity=0.75):
        return {
            "compound_id": f"cs-{uuid.uuid4().hex[:8]}",
            "rule_id": rule_id,
            "severity_score": severity,
            "narrative": "Test correlation detected",
            "temporal_window_hours": 168,
            "member_events": json.dumps([
                {"source_type": "bill", "event_id": "b1", "title": "Bill A", "timestamp": "2026-01-01"},
                {"source_type": "oversight", "event_id": "o1", "title": "Report A", "timestamp": "2026-01-02"},
            ]),
            "topics": json.dumps(["disability_benefits"]),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def test_insert_compound_signal(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.db.compound import insert_compound_signal
            data = self._make_signal_data()
            result = insert_compound_signal(data)
            assert result == data["compound_id"]

    def test_get_compound_signal(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.db.compound import insert_compound_signal, get_compound_signal
            data = self._make_signal_data()
            insert_compound_signal(data)
            row = get_compound_signal(data["compound_id"])
            assert row is not None
            assert row["compound_id"] == data["compound_id"]
            assert row["rule_id"] == data["rule_id"]
            assert row["severity_score"] == data["severity_score"]

    def test_get_compound_signal_not_found(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.db.compound import get_compound_signal
            row = get_compound_signal("nonexistent-id")
            assert row is None

    def test_get_compound_signals_default(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.db.compound import insert_compound_signal, get_compound_signals
            for i in range(5):
                insert_compound_signal(self._make_signal_data())
            rows = get_compound_signals()
            assert len(rows) == 5

    def test_get_compound_signals_limit(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.db.compound import insert_compound_signal, get_compound_signals
            for i in range(5):
                insert_compound_signal(self._make_signal_data())
            rows = get_compound_signals(limit=3)
            assert len(rows) == 3

    def test_get_compound_signals_offset(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.db.compound import insert_compound_signal, get_compound_signals
            for i in range(5):
                insert_compound_signal(self._make_signal_data())
            rows = get_compound_signals(limit=10, offset=3)
            assert len(rows) == 2

    def test_get_compound_signals_filter_by_rule(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.db.compound import insert_compound_signal, get_compound_signals
            insert_compound_signal(self._make_signal_data(rule_id="rule_a"))
            insert_compound_signal(self._make_signal_data(rule_id="rule_b"))
            insert_compound_signal(self._make_signal_data(rule_id="rule_a"))
            rows = get_compound_signals(rule_id="rule_a")
            assert len(rows) == 2
            assert all(r["rule_id"] == "rule_a" for r in rows)

    def test_get_compound_signals_filter_by_severity(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.db.compound import insert_compound_signal, get_compound_signals
            insert_compound_signal(self._make_signal_data(severity=0.3))
            insert_compound_signal(self._make_signal_data(severity=0.7))
            insert_compound_signal(self._make_signal_data(severity=0.9))
            rows = get_compound_signals(min_severity=0.6)
            assert len(rows) == 2
            assert all(r["severity_score"] >= 0.6 for r in rows)

    def test_resolve_compound_signal(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.db.compound import insert_compound_signal, resolve_compound_signal, get_compound_signal
            data = self._make_signal_data()
            insert_compound_signal(data)
            result = resolve_compound_signal(data["compound_id"])
            assert result is True
            row = get_compound_signal(data["compound_id"])
            assert row["resolved_at"] is not None

    def test_resolve_nonexistent_returns_false(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.db.compound import resolve_compound_signal
            result = resolve_compound_signal("nonexistent-id")
            assert result is False

    def test_get_compound_stats(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.db.compound import insert_compound_signal, get_compound_stats, resolve_compound_signal
            d1 = self._make_signal_data(rule_id="rule_a", severity=0.8)
            d2 = self._make_signal_data(rule_id="rule_b", severity=0.5)
            d3 = self._make_signal_data(rule_id="rule_a", severity=0.9)
            insert_compound_signal(d1)
            insert_compound_signal(d2)
            insert_compound_signal(d3)
            resolve_compound_signal(d2["compound_id"])

            stats = get_compound_stats()
            assert stats["total"] == 3
            assert stats["unresolved"] == 2
            assert stats["resolved"] == 1
            assert "rule_a" in stats["by_rule"]
            assert stats["by_rule"]["rule_a"] == 2
            assert stats["by_rule"]["rule_b"] == 1

    def test_insert_duplicate_compound_id_ignored(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.db.compound import insert_compound_signal, get_compound_signals
            data = self._make_signal_data()
            insert_compound_signal(data)
            # Second insert with same compound_id should be ignored
            result = insert_compound_signal(data)
            assert result is None
            rows = get_compound_signals()
            assert len(rows) == 1


# ===========================================================================
# Tests: MemberEvent Dataclass
# ===========================================================================


class TestMemberEvent:
    """Test MemberEvent dataclass."""

    def test_member_event_creation(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import MemberEvent
            ev = MemberEvent(
                source_type="bill",
                event_id="b1",
                title="Test Bill",
                timestamp="2026-01-01T00:00:00",
                topics=["disability_benefits"],
                metadata={"congress": 119},
            )
            assert ev.source_type == "bill"
            assert ev.event_id == "b1"
            assert ev.title == "Test Bill"
            assert "disability_benefits" in ev.topics

    def test_member_event_to_dict(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import MemberEvent
            ev = MemberEvent(
                source_type="oversight",
                event_id="o1",
                title="GAO Report",
                timestamp="2026-01-01",
                topics=["claims_backlog"],
                metadata={},
            )
            d = ev.to_dict()
            assert d["source_type"] == "oversight"
            assert d["event_id"] == "o1"
            assert d["title"] == "GAO Report"
            assert d["timestamp"] == "2026-01-01"


# ===========================================================================
# Tests: CompoundSignal Dataclass
# ===========================================================================


class TestCompoundSignal:
    """Test CompoundSignal dataclass."""

    def test_compound_signal_creation(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CompoundSignal, MemberEvent
            events = [
                MemberEvent("bill", "b1", "Bill", "2026-01-01", ["disability_benefits"], {}),
                MemberEvent("oversight", "o1", "Report", "2026-01-02", ["disability_benefits"], {}),
            ]
            sig = CompoundSignal(
                compound_id="cs-123",
                rule_id="test_rule",
                severity_score=0.75,
                narrative="Test narrative",
                temporal_window_hours=168,
                member_events=events,
                topics=["disability_benefits"],
                created_at="2026-01-03T00:00:00",
            )
            assert sig.compound_id == "cs-123"
            assert len(sig.member_events) == 2

    def test_compound_signal_to_db_dict(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CompoundSignal, MemberEvent
            events = [
                MemberEvent("bill", "b1", "Bill", "2026-01-01", ["x"], {}),
            ]
            sig = CompoundSignal(
                compound_id="cs-456",
                rule_id="rule_a",
                severity_score=0.8,
                narrative="Test",
                temporal_window_hours=336,
                member_events=events,
                topics=["x"],
                created_at="2026-01-03T00:00:00",
            )
            d = sig.to_db_dict()
            assert d["compound_id"] == "cs-456"
            assert isinstance(d["member_events"], str)  # JSON serialized
            assert isinstance(d["topics"], str)
            parsed_events = json.loads(d["member_events"])
            assert len(parsed_events) == 1


# ===========================================================================
# Tests: Migration
# ===========================================================================


class TestMigration:
    """Test the schema migration creates the compound_signals table."""

    @staticmethod
    def _load_migration():
        import importlib.util
        script = ROOT / "migrations" / "008_add_compound_signals.py"
        spec = importlib.util.spec_from_file_location("m008", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_migration_creates_table(self, tmp_path):
        db_path = tmp_path / "migration_test.db"
        con = sqlite3.connect(str(db_path), timeout=30)
        con.execute("PRAGMA journal_mode=WAL")
        con.close()

        with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
            with patch("src.db.core.DB_PATH", db_path):
                m008 = self._load_migration()
                m008.run_migration()

                con = sqlite3.connect(str(db_path), timeout=30)
                cur = con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='compound_signals'"
                )
                assert cur.fetchone() is not None
                con.close()

    def test_migration_is_idempotent(self, tmp_path):
        db_path = tmp_path / "migration_test.db"
        con = sqlite3.connect(str(db_path), timeout=30)
        con.execute("PRAGMA journal_mode=WAL")
        con.close()

        with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
            with patch("src.db.core.DB_PATH", db_path):
                m008 = self._load_migration()
                m008.run_migration()
                m008.run_migration()  # Should not fail


# ===========================================================================
# Tests: Integration (Engine + DB)
# ===========================================================================


class TestEngineIntegration:
    """Test end-to-end: engine evaluates rules and stores results."""

    def test_run_stores_compound_signals(self, populated_db, rules_path):
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            from src.db.compound import get_compound_signals
            engine = CorrelationEngine(rules_path=rules_path)
            summary = engine.run()
            assert summary["total_signals"] > 0
            rows = get_compound_signals()
            assert len(rows) > 0

    def test_run_idempotent(self, populated_db, rules_path):
        """Running twice doesn't create duplicates."""
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            from src.db.compound import get_compound_signals
            engine = CorrelationEngine(rules_path=rules_path)
            engine.run()
            count_1 = len(get_compound_signals(limit=100))
            engine.run()
            count_2 = len(get_compound_signals(limit=100))
            assert count_2 == count_1

    def test_run_with_empty_db(self, tmp_db):
        with patch("src.db.core.DB_PATH", tmp_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine()
            summary = engine.run()
            assert summary["total_signals"] == 0

    def test_run_with_no_rules(self, populated_db, tmp_path):
        rules_path = tmp_path / "empty_rules.yaml"
        rules_path.write_text("[]")
        with patch("src.db.core.DB_PATH", populated_db):
            from src.signals.correlator import CorrelationEngine
            engine = CorrelationEngine(rules_path=rules_path)
            summary = engine.run()
            assert summary["total_signals"] == 0
