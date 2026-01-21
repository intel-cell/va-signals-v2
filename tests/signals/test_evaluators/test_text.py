"""Tests for text evaluators."""

import pytest
from src.signals.envelope import Envelope
from src.signals.evaluators.text import ContainsAnyEvaluator


@pytest.fixture
def sample_envelope():
    return Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="VA Hearing on GAO Report",
        body_text="The GAO found issues with OIG oversight of disability claims.",
    )


def test_contains_any_matches(sample_envelope):
    evaluator = ContainsAnyEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="body_text",
        terms=["GAO", "OIG", "audit"],
    )
    assert result["passed"] is True
    assert "GAO" in result["evidence"]["matched_terms"]
    assert "OIG" in result["evidence"]["matched_terms"]


def test_contains_any_no_match(sample_envelope):
    evaluator = ContainsAnyEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="body_text",
        terms=["VASRD", "modernization"],
    )
    assert result["passed"] is False
    assert result["evidence"]["matched_terms"] == []


def test_contains_any_case_insensitive(sample_envelope):
    evaluator = ContainsAnyEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="body_text",
        terms=["gao", "oig"],  # lowercase
    )
    assert result["passed"] is True
    assert len(result["evidence"]["matched_terms"]) == 2


def test_contains_any_title_field(sample_envelope):
    evaluator = ContainsAnyEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="title",
        terms=["GAO Report"],
    )
    assert result["passed"] is True


def test_contains_any_invalid_field(sample_envelope):
    evaluator = ContainsAnyEvaluator()
    with pytest.raises(ValueError, match="not in allowed fields"):
        evaluator.evaluate(
            sample_envelope,
            field="invalid_field",
            terms=["test"],
        )
