"""Tests for normalized event envelope."""

import pytest
from src.signals.envelope import Envelope, normalize_text, compute_content_hash


def test_envelope_creation():
    env = Envelope(
        event_id="om-gao-abc123",
        authority_id="GAO-26-106123",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test Hearing",
        body_text="This is the body text.",
    )
    assert env.event_id == "om-gao-abc123"
    assert env.authority_source == "congress_gov"
    assert env.version == 1  # Default


def test_envelope_with_optional_fields():
    env = Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="govinfo",
        authority_type="rule",
        title="Test Rule",
        body_text="Body",
        committee="HVAC",
        topics=["disability_benefits", "rating"],
        metadata={"status": "scheduled"},
    )
    assert env.committee == "HVAC"
    assert env.topics == ["disability_benefits", "rating"]
    assert env.metadata["status"] == "scheduled"


def test_normalize_text():
    # Case insensitive, NFKC, whitespace collapse
    text = "  GAO   Report  "
    normalized = normalize_text(text)
    assert normalized == "gao report"


def test_normalize_text_preserves_punctuation():
    text = "O.I.G. Report"
    normalized = normalize_text(text)
    assert normalized == "o.i.g. report"


def test_compute_content_hash():
    hash1 = compute_content_hash("Title", "Body")
    hash2 = compute_content_hash("Title", "Body")
    hash3 = compute_content_hash("Title", "Different")
    assert hash1 == hash2
    assert hash1 != hash3
    assert hash1.startswith("sha256:")
