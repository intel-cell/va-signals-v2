"""Tests for expression evaluator."""

import pytest
from src.signals.envelope import Envelope
from src.signals.engine.evaluator import evaluate_expression, EvaluationResult


@pytest.fixture
def gao_envelope():
    return Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Hearing on GAO Report",
        body_text="The GAO found issues with VA disability claims processing.",
        committee="HVAC",
        topics=["disability_benefits", "claims_backlog"],
        version=1,
    )


def test_evaluate_simple_evaluator(gao_envelope):
    expr = {
        "evaluator": "contains_any",
        "args": {"field": "body_text", "terms": ["GAO", "OIG"]},
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is True
    assert "GAO" in result.matched_terms


def test_evaluate_all_of_passes(gao_envelope):
    expr = {
        "all_of": [
            {"evaluator": "contains_any", "args": {"field": "body_text", "terms": ["GAO"]}},
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["HVAC", "SVAC"]}},
        ]
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is True


def test_evaluate_all_of_fails(gao_envelope):
    expr = {
        "all_of": [
            {"evaluator": "contains_any", "args": {"field": "body_text", "terms": ["GAO"]}},
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["SASC"]}},
        ]
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is False


def test_evaluate_any_of_passes(gao_envelope):
    expr = {
        "any_of": [
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["SASC"]}},
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["HVAC"]}},
        ],
        "label": "discriminator",
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is True
    assert "field_in(committee)" in result.matched_discriminators


def test_evaluate_collects_evidence(gao_envelope):
    expr = {
        "all_of": [
            {"evaluator": "contains_any", "args": {"field": "body_text", "terms": ["GAO", "OIG"]}},
            {
                "any_of": [
                    {"evaluator": "field_in", "args": {"field": "committee", "values": ["HVAC"]}},
                ],
                "label": "anti_spam_discriminator",
            },
        ]
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is True
    assert len(result.passed_evaluators) >= 2
    assert len(result.evidence_map) >= 2


def test_evaluate_tracks_failed_evaluators(gao_envelope):
    expr = {
        "all_of": [
            {"evaluator": "contains_any", "args": {"field": "body_text", "terms": ["VASRD"]}},
        ]
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is False
    assert len(result.failed_evaluators) > 0


def test_evaluate_none_of_passes(gao_envelope):
    """none_of passes when none of the child expressions match."""
    expr = {
        "none_of": [
            {"evaluator": "contains_any", "args": {"field": "body_text", "terms": ["VASRD"]}},
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["SASC"]}},
        ]
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is True


def test_evaluate_none_of_fails(gao_envelope):
    """none_of fails when any of the child expressions match."""
    expr = {
        "none_of": [
            {"evaluator": "contains_any", "args": {"field": "body_text", "terms": ["GAO"]}},
        ]
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is False
