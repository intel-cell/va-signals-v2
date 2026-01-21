"""Tests for comparison evaluators."""

import pytest
from src.signals.envelope import Envelope
from src.signals.evaluators.comparison import EqualsEvaluator, GtEvaluator


@pytest.fixture
def sample_envelope():
    return Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test",
        body_text="Body",
        version=2,
    )


# EqualsEvaluator tests
def test_equals_matches(sample_envelope):
    evaluator = EqualsEvaluator()
    result = evaluator.evaluate(sample_envelope, field="version", value=2)
    assert result["passed"] is True
    assert result["evidence"]["actual_value"] == 2
    assert result["evidence"]["expected_value"] == 2


def test_equals_no_match(sample_envelope):
    evaluator = EqualsEvaluator()
    result = evaluator.evaluate(sample_envelope, field="version", value=1)
    assert result["passed"] is False


def test_equals_string_match(sample_envelope):
    evaluator = EqualsEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="authority_type",
        value="hearing_notice",
    )
    assert result["passed"] is True


# GtEvaluator tests
def test_gt_passes(sample_envelope):
    evaluator = GtEvaluator()
    result = evaluator.evaluate(sample_envelope, field="version", value=1)
    assert result["passed"] is True
    assert result["evidence"]["actual_value"] == 2
    assert result["evidence"]["threshold"] == 1


def test_gt_fails_equal(sample_envelope):
    evaluator = GtEvaluator()
    result = evaluator.evaluate(sample_envelope, field="version", value=2)
    assert result["passed"] is False


def test_gt_fails_less(sample_envelope):
    evaluator = GtEvaluator()
    result = evaluator.evaluate(sample_envelope, field="version", value=3)
    assert result["passed"] is False


def test_gt_null_field():
    env = Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test",
        body_text="Body",
    )
    evaluator = GtEvaluator()
    # version defaults to 1
    result = evaluator.evaluate(env, field="version", value=0)
    assert result["passed"] is True
