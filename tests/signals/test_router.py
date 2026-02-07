"""Tests for signals router."""

import pytest

from src.signals.envelope import Envelope
from src.signals.router import RouteResult, SignalsRouter


@pytest.fixture
def router(tmp_path, monkeypatch):
    """Create router with test DB for suppression."""
    import src.db as db_module

    test_db = tmp_path / "test_signals.db"
    monkeypatch.setattr(db_module, "DB_PATH", test_db)
    db_module.init_db()
    return SignalsRouter(categories=["oversight_accountability"])


@pytest.fixture
def gao_envelope():
    return Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Hearing on GAO Report",
        body_text="The GAO found issues with VA disability claims. This is an investigation.",
        committee="HVAC",
        topics=["disability_benefits"],
        version=1,
    )


def test_router_matches_trigger(router, gao_envelope):
    results = router.route(gao_envelope)
    assert len(results) > 0
    assert any(r.trigger_id == "formal_audit_signal" for r in results)


def test_router_returns_route_result(router, gao_envelope):
    results = router.route(gao_envelope)
    result = results[0]
    assert isinstance(result, RouteResult)
    assert result.indicator_id is not None
    assert result.trigger_id is not None
    assert result.severity in ["low", "medium", "high", "critical"]


def test_router_respects_indicator_condition(router):
    # Envelope from non-matching authority source
    env = Envelope(
        event_id="test-2",
        authority_id="AUTH-2",
        authority_source="govinfo",  # Not congress_gov
        authority_type="rule",
        title="Test Rule",
        body_text="GAO found issues",
        version=1,
    )
    results = router.route(env)
    # Should not match gao_oig_reference indicator (requires congress_gov source)
    assert not any(r.indicator_id == "gao_oig_reference" for r in results)


def test_router_returns_severity_and_actions(router, gao_envelope):
    results = router.route(gao_envelope)
    # formal_audit_signal should have high severity
    formal_audit = [r for r in results if r.trigger_id == "formal_audit_signal"]
    assert len(formal_audit) > 0
    assert formal_audit[0].severity == "high"
    assert "post_slack_alert" in formal_audit[0].actions


def test_router_includes_evaluation_result(router, gao_envelope):
    results = router.route(gao_envelope)
    result = results[0]
    assert result.evaluation is not None
    assert result.evaluation.passed is True
    # Should have matched terms from contains_any evaluator
    assert (
        "GAO" in result.evaluation.matched_terms
        or "investigation" in result.evaluation.matched_terms
    )


def test_router_checks_suppression(router, gao_envelope):
    # First route - not suppressed
    results1 = router.route(gao_envelope)
    assert len(results1) > 0
    assert results1[0].suppressed is False

    # Record the fire for suppression
    for r in results1:
        if not r.suppressed:
            router.suppression.record_fire(
                r.trigger_id,
                gao_envelope.authority_id,
                gao_envelope.version,
                60,  # cooldown
            )

    # Second route - should be suppressed
    results2 = router.route(gao_envelope)
    suppressed_results = [r for r in results2 if r.suppressed]
    assert len(suppressed_results) > 0


def test_router_returns_empty_for_no_matches(router):
    # Envelope that doesn't match any triggers
    env = Envelope(
        event_id="test-3",
        authority_id="AUTH-3",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Unrelated Hearing",
        body_text="This hearing is about transportation infrastructure.",
        committee="Transportation",
        topics=["transportation"],
        version=1,
    )
    results = router.route(env)
    # May have some results, but not for VA-specific triggers
    formal_audit = [r for r in results if r.trigger_id == "formal_audit_signal"]
    assert len(formal_audit) == 0
