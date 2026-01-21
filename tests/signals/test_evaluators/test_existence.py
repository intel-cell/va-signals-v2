"""Tests for existence and nested field evaluators."""

import pytest
from src.signals.envelope import Envelope
from src.signals.evaluators.existence import FieldExistsEvaluator, NestedFieldInEvaluator


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
        metadata={"status": "cancelled", "priority": "high"},
    )


# FieldExistsEvaluator tests
def test_field_exists_true(sample_envelope):
    evaluator = FieldExistsEvaluator()
    result = evaluator.evaluate(sample_envelope, field="committee")
    assert result["passed"] is True
    assert result["evidence"]["field_present"] is True


def test_field_exists_false():
    env = Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test",
        body_text="Body",
        committee=None,
    )
    evaluator = FieldExistsEvaluator()
    result = evaluator.evaluate(env, field="committee")
    assert result["passed"] is False
    assert result["evidence"]["field_present"] is False


# NestedFieldInEvaluator tests
def test_nested_field_in_matches(sample_envelope):
    evaluator = NestedFieldInEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="metadata.status",
        values=["cancelled", "rescheduled", "postponed"],
    )
    assert result["passed"] is True
    assert result["evidence"]["actual_value"] == "cancelled"
    assert result["evidence"]["matched"] is True


def test_nested_field_in_no_match(sample_envelope):
    evaluator = NestedFieldInEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="metadata.status",
        values=["scheduled"],
    )
    assert result["passed"] is False


def test_nested_field_in_missing_key(sample_envelope):
    evaluator = NestedFieldInEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="metadata.nonexistent",
        values=["value"],
    )
    assert result["passed"] is False
    assert result["evidence"]["actual_value"] is None


def test_nested_field_in_invalid_prefix(sample_envelope):
    evaluator = NestedFieldInEvaluator()
    with pytest.raises(ValueError, match="not in allowed fields"):
        evaluator.evaluate(
            sample_envelope,
            field="invalid.field",
            values=["value"],
        )
