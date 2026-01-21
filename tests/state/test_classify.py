"""Tests for state intelligence classification."""

import pytest

from src.state.classify import (
    HIGH_SEVERITY_KEYWORDS,
    MEDIUM_SEVERITY_KEYWORDS,
    ClassificationResult,
    classify_by_keywords,
)


def test_classification_result_creation():
    result = ClassificationResult(
        severity="high",
        method="keyword",
        keywords_matched=["suspend"],
    )
    assert result.severity == "high"
    assert "suspend" in result.keywords_matched


def test_classify_high_severity_suspend():
    result = classify_by_keywords(
        title="Texas Veterans Commission suspends PACT Act program",
        content="The commission announced a suspension...",
    )
    assert result.severity == "high"
    # Matches word forms like "suspends", "suspension"
    assert any("suspend" in kw for kw in result.keywords_matched)


def test_classify_high_severity_backlog():
    result = classify_by_keywords(
        title="VA reports backlog in benefits claims",
        content="A significant backlog has developed...",
    )
    assert result.severity == "high"
    assert "backlog" in result.keywords_matched


def test_classify_high_severity_investigation():
    result = classify_by_keywords(
        title="Investigation launched into VA facility",
        content="State officials have launched an investigation...",
    )
    assert result.severity == "high"
    assert "investigation" in result.keywords_matched


def test_classify_medium_severity_resign():
    result = classify_by_keywords(
        title="CalVet Director to resign next month",
        content="The director announced plans to resign...",
    )
    assert result.severity == "medium"
    assert "resign" in result.keywords_matched


def test_classify_medium_severity_reform():
    result = classify_by_keywords(
        title="Florida announces VA healthcare reform",
        content="Major reforms are planned...",
    )
    assert result.severity == "medium"
    assert "reform" in result.keywords_matched


def test_classify_low_severity_routine():
    result = classify_by_keywords(
        title="Veterans Day ceremony held at state capitol",
        content="State officials gathered to honor veterans...",
    )
    assert result.severity == "low"
    assert len(result.keywords_matched) == 0


def test_classify_multiple_keywords():
    result = classify_by_keywords(
        title="Investigation reveals budget cut failures",
        content="The investigation found budget cuts led to failures...",
    )
    assert result.severity == "high"
    # Should match multiple high-severity keywords
    assert len(result.keywords_matched) >= 2


def test_classify_case_insensitive():
    """Verify case-insensitive matching."""
    result = classify_by_keywords(
        title="INVESTIGATION LAUNCHED INTO VA FACILITY",
        content="",
    )
    assert result.severity == "high"
    assert "investigation" in result.keywords_matched


def test_classify_word_boundaries_no_false_positive():
    """Verify word boundaries prevent false positives."""
    # "paid" contains "aid" but should not trigger
    result = classify_by_keywords(
        title="Veterans group paid tribute to local heroes",
        content="The celebration was said to be a success",
    )
    assert result.severity == "low"


def test_classify_content_only():
    """Verify content-only matching works."""
    result = classify_by_keywords(
        title="State News Update",
        content="Officials announced a suspension of the program",
    )
    assert result.severity == "high"
    assert "suspension" in result.keywords_matched


def test_classify_empty_content():
    """Verify empty content is handled."""
    result = classify_by_keywords(
        title="Veterans Day Event",
        content="",
    )
    assert result.severity == "low"


def test_classify_none_content():
    """Verify None content is handled."""
    result = classify_by_keywords(
        title="Veterans Day Event",
        content=None,
    )
    assert result.severity == "low"
