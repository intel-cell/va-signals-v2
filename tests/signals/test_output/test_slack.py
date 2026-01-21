"""Tests for Slack alert formatter."""

import pytest
from src.signals.output.slack import format_slack_alert
from src.signals.engine.evaluator import EvaluationResult


def test_format_slack_alert_basic():
    result = EvaluationResult(
        passed=True,
        matched_terms=["GAO"],
        matched_discriminators=["field_in(committee)"],
    )

    payload = format_slack_alert(
        event_id="test-1",
        authority_id="AUTH-1",
        indicator_id="gao_oig_reference",
        trigger_id="formal_audit_signal",
        severity="high",
        title="GAO Report on VA Claims",
        result=result,
    )

    assert "blocks" in payload
    assert "text" in payload
    assert "formal_audit_signal" in payload["text"]


def test_format_slack_alert_includes_severity_emoji():
    result = EvaluationResult(passed=True)

    # High severity
    payload = format_slack_alert(
        event_id="test",
        authority_id="auth",
        indicator_id="ind",
        trigger_id="trig",
        severity="high",
        title="Test",
        result=result,
    )
    assert "\U0001F7E0" in payload["text"]  # orange circle

    # Critical severity
    payload = format_slack_alert(
        event_id="test",
        authority_id="auth",
        indicator_id="ind",
        trigger_id="trig",
        severity="critical",
        title="Test",
        result=result,
    )
    assert "\U0001F534" in payload["text"]  # red circle


def test_format_slack_alert_includes_source_url():
    result = EvaluationResult(passed=True)

    payload = format_slack_alert(
        event_id="test",
        authority_id="auth",
        indicator_id="ind",
        trigger_id="trig",
        severity="medium",
        title="Test",
        result=result,
        source_url="https://example.com/doc",
    )

    # Check for link block
    blocks_text = str(payload["blocks"])
    assert "example.com" in blocks_text


def test_format_slack_alert_human_review():
    result = EvaluationResult(passed=True)

    payload = format_slack_alert(
        event_id="test",
        authority_id="auth",
        indicator_id="ind",
        trigger_id="trig",
        severity="high",
        title="Test",
        result=result,
        human_review_required=True,
    )

    blocks_text = str(payload["blocks"])
    assert "Human review required" in blocks_text
