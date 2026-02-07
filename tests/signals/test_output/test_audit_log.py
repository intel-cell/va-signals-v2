"""Tests for audit log writer."""

import json

import pytest

from src.db import connect
from src.signals.engine.evaluator import EvaluationResult
from src.signals.output.audit_log import write_audit_log


@pytest.fixture
def setup_db(tmp_path, monkeypatch):
    """Set up test database."""
    import src.db as db_module

    test_db = tmp_path / "test_signals.db"
    monkeypatch.setattr(db_module, "DB_PATH", test_db)
    db_module.init_db()
    yield


def test_write_audit_log_returns_id(setup_db):
    result = EvaluationResult(
        passed=True,
        matched_terms=["GAO"],
        matched_discriminators=["field_in(committee)"],
        passed_evaluators=["contains_any(body_text)"],
        failed_evaluators=[],
        evidence_map={"test": {"passed": True}},
    )

    row_id = write_audit_log(
        event_id="test-1",
        authority_id="AUTH-1",
        indicator_id="gao_oig_reference",
        trigger_id="formal_audit_signal",
        severity="high",
        result=result,
    )

    assert row_id > 0


def test_write_audit_log_stores_suppressed(setup_db):
    result = EvaluationResult(passed=True)

    row_id = write_audit_log(
        event_id="test-2",
        authority_id="AUTH-2",
        indicator_id="ind",
        trigger_id="trig",
        severity="medium",
        result=result,
        suppressed=True,
        suppression_reason="cooldown",
    )

    # Verify stored correctly
    con = connect()
    cur = con.cursor()
    cur.execute(
        "SELECT suppressed, suppression_reason FROM signal_audit_log WHERE id = ?", (row_id,)
    )
    row = cur.fetchone()
    con.close()

    assert row[0] == 1
    assert row[1] == "cooldown"


def test_write_audit_log_stores_explanation(setup_db):
    result = EvaluationResult(
        passed=True,
        matched_terms=["GAO", "OIG"],
        matched_discriminators=["disc1"],
        passed_evaluators=["eval1", "eval2"],
        failed_evaluators=["eval3"],
        evidence_map={"key": {"evidence": "data"}},
    )

    row_id = write_audit_log(
        event_id="test-3",
        authority_id="AUTH-3",
        indicator_id="ind",
        trigger_id="trig",
        severity="high",
        result=result,
    )

    con = connect()
    cur = con.cursor()
    cur.execute("SELECT explanation_json FROM signal_audit_log WHERE id = ?", (row_id,))
    row = cur.fetchone()
    con.close()

    explanation = json.loads(row[0])
    assert explanation["matched_terms"] == ["GAO", "OIG"]
    assert "disc1" in explanation["matched_discriminators"]
    assert len(explanation["passed_evaluators"]) == 2
