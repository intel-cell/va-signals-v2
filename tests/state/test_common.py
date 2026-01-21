"""Tests for state intelligence common utilities."""

import pytest

from src.state.common import (
    RawSignal,
    generate_signal_id,
    detect_program,
    VETERAN_KEYWORDS,
    is_veteran_relevant,
)


def test_raw_signal_creation():
    signal = RawSignal(
        url="https://example.com/news/1",
        title="PACT Act Outreach Event",
        content="Veterans are invited...",
        pub_date="2026-01-20",
        source_id="tx_tvc_news",
        state="TX",
    )
    assert signal.url == "https://example.com/news/1"
    assert signal.state == "TX"


def test_generate_signal_id():
    url = "https://tvc.texas.gov/news/pact-act-event"
    signal_id = generate_signal_id(url)
    assert signal_id is not None
    assert len(signal_id) == 64  # SHA-256 hex


def test_generate_signal_id_deterministic():
    url = "https://example.com/test"
    id1 = generate_signal_id(url)
    id2 = generate_signal_id(url)
    assert id1 == id2


def test_detect_program_pact_act():
    text = "Texas announces PACT Act toxic exposure screening initiative"
    program = detect_program(text)
    assert program == "pact_act"


def test_detect_program_community_care():
    text = "VA community care network adds new providers"
    program = detect_program(text)
    assert program == "community_care"


def test_detect_program_vha():
    text = "Veterans Health Administration facility coordination"
    program = detect_program(text)
    assert program == "vha"


def test_detect_program_none():
    text = "General veterans news about job fair"
    program = detect_program(text)
    assert program is None


def test_is_veteran_relevant_true():
    text = "Texas Veterans Commission announces new program"
    assert is_veteran_relevant(text) is True


def test_is_veteran_relevant_false():
    text = "Local bakery opens new location"
    assert is_veteran_relevant(text) is False


def test_is_veteran_relevant_va_mention():
    text = "VA healthcare expansion announced"
    assert is_veteran_relevant(text) is True


def test_detect_program_case_insensitive():
    text = "PACT ACT INITIATIVE ANNOUNCED"
    program = detect_program(text)
    assert program == "pact_act"


def test_is_veteran_relevant_false_positive_java():
    """Verify 'java' doesn't match as veteran-relevant."""
    text = "Java programming tutorial available"
    assert is_veteran_relevant(text) is False


def test_is_veteran_relevant_false_positive_evacuation():
    """Verify 'evacuation' doesn't match."""
    text = "Emergency evacuation plans released"
    assert is_veteran_relevant(text) is False


def test_detect_program_empty_string():
    assert detect_program("") is None


def test_is_veteran_relevant_empty_string():
    assert is_veteran_relevant("") is False
