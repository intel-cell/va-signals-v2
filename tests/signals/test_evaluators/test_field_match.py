"""Tests for field match evaluators."""

import pytest
from src.signals.envelope import Envelope
from src.signals.evaluators.field_match import FieldInEvaluator, FieldIntersectsEvaluator


@pytest.fixture
def sample_envelope():
    return Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test",
        body_text="Body",
        committee="HVAC",
        topics=["disability_benefits", "exam_quality"],
    )


# FieldInEvaluator tests
def test_field_in_matches(sample_envelope):
    evaluator = FieldInEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="committee",
        values=["HVAC", "SVAC"],
    )
    assert result["passed"] is True
    assert result["evidence"]["actual_value"] == "HVAC"
    assert result["evidence"]["matched"] is True


def test_field_in_no_match(sample_envelope):
    evaluator = FieldInEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="committee",
        values=["HASC", "SASC"],
    )
    assert result["passed"] is False
    assert result["evidence"]["matched"] is False


def test_field_in_null_value():
    env = Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test",
        body_text="Body",
        committee=None,
    )
    evaluator = FieldInEvaluator()
    result = evaluator.evaluate(env, field="committee", values=["HVAC"])
    assert result["passed"] is False


# FieldIntersectsEvaluator tests
def test_field_intersects_matches(sample_envelope):
    evaluator = FieldIntersectsEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="topics",
        values=["disability_benefits", "rating"],
    )
    assert result["passed"] is True
    assert "disability_benefits" in result["evidence"]["intersection"]


def test_field_intersects_no_match(sample_envelope):
    evaluator = FieldIntersectsEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="topics",
        values=["vasrd", "appeals"],
    )
    assert result["passed"] is False
    assert result["evidence"]["intersection"] == []


def test_field_intersects_empty_field():
    env = Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test",
        body_text="Body",
        topics=[],
    )
    evaluator = FieldIntersectsEvaluator()
    result = evaluator.evaluate(env, field="topics", values=["rating"])
    assert result["passed"] is False
