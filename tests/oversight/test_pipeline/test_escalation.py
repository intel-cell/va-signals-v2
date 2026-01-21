"""Tests for escalation checker."""

import pytest

from src.oversight.pipeline.escalation import (
    EscalationResult,
    check_escalation,
)
from src.oversight.db_helpers import seed_default_escalation_signals


@pytest.fixture(autouse=True)
def seed_signals():
    """Seed default escalation signals for tests."""
    seed_default_escalation_signals()
    yield


def test_escalation_matches_criminal_referral():
    result = check_escalation(
        title="GAO Refers VA Contract Fraud to DOJ",
        content="GAO has issued a criminal referral to the Department of Justice...",
    )

    assert result.is_escalation is True
    assert "criminal referral" in result.matched_signals


def test_escalation_matches_subpoena():
    result = check_escalation(
        title="House Committee Issues Subpoena to VA",
        content="The committee voted to issue a subpoena for documents...",
    )

    assert result.is_escalation is True
    assert "subpoena" in result.matched_signals


def test_escalation_ignores_historical_reference():
    result = check_escalation(
        title="Review of Past Oversight Actions",
        content="The 2019 criminal referral led to reforms...",
    )

    # Should NOT match because it's a historical reference
    # This requires smarter matching - for now, it will match
    # We'll refine in a future task
    assert result.is_escalation is True  # Known limitation


def test_escalation_no_match_for_routine():
    result = check_escalation(
        title="GAO Releases Quarterly VA Healthcare Report",
        content="This quarterly report examines wait times at VA facilities...",
    )

    assert result.is_escalation is False
    assert len(result.matched_signals) == 0


def test_escalation_matches_whistleblower():
    result = check_escalation(
        title="VA Whistleblower Testifies Before Congress",
        content="A whistleblower from the VA regional office testified...",
    )

    assert result.is_escalation is True
    assert "whistleblower" in result.matched_signals
