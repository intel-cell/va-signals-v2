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
    assert "suspend" in result.keywords_matched


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
