"""Tests for escalation priority scoring (Phase 1)."""

from src.oversight.pipeline.priority import (
    ALERT_THRESHOLD,
    WEBSOCKET_THRESHOLD,
    compute_escalation_priority,
)


def _make_event(**overrides) -> dict:
    """Helper to build a minimal event dict."""
    event = {
        "event_id": "om-test-001",
        "title": "Test Event",
        "primary_source_type": "gao",
        "is_escalation": True,
    }
    event.update(overrides)
    return event


def test_critical_gao_event():
    """Critical GAO event with high ML score should score >= 0.80."""
    result = compute_escalation_priority(
        event=_make_event(),
        ml_score=0.95,
        escalation_signal_count=4,
        escalation_severity="critical",
        source_type="gao",
    )
    assert result.priority_score >= 0.80
    assert result.priority_level == "critical"
    assert result.should_alert is True
    assert result.should_push_websocket is True


def test_low_news_wire_no_signals():
    """Low-severity news wire with no signals should score < 0.40."""
    result = compute_escalation_priority(
        event=_make_event(),
        ml_score=0.1,
        escalation_signal_count=0,
        escalation_severity="none",
        source_type="news_wire",
    )
    assert result.priority_score < 0.40
    assert result.should_alert is False
    assert result.should_push_websocket is False


def test_ml_score_none_redistribution():
    """When ml_score is None, weights redistribute across other components."""
    result = compute_escalation_priority(
        event=_make_event(),
        ml_score=None,
        escalation_signal_count=3,
        escalation_severity="high",
        source_type="oig",
    )
    assert result.component_scores["ml_score"] is None
    # OIG + high severity + 3 signals should still score well
    assert result.priority_score >= 0.50
    assert result.should_push_websocket is True


def test_alert_threshold_boundary():
    """Score exactly at the alert threshold should trigger alert."""
    # Build inputs that push close to 0.60
    result = compute_escalation_priority(
        event=_make_event(),
        ml_score=0.60,
        escalation_signal_count=2,
        escalation_severity="medium",
        source_type="crs",
    )
    # Exact boundary may vary; just check consistency of flags
    if result.priority_score >= ALERT_THRESHOLD:
        assert result.should_alert is True
    else:
        assert result.should_alert is False


def test_websocket_threshold_boundary():
    """Score just below websocket threshold should NOT push."""
    result = compute_escalation_priority(
        event=_make_event(),
        ml_score=0.2,
        escalation_signal_count=1,
        escalation_severity="low",
        source_type="trade_press",
    )
    if result.priority_score < WEBSOCKET_THRESHOLD:
        assert result.should_push_websocket is False


def test_component_scores_breakdown():
    """Component scores dict should contain all expected keys."""
    result = compute_escalation_priority(
        event=_make_event(),
        ml_score=0.7,
        escalation_signal_count=2,
        escalation_severity="high",
        source_type="gao",
    )
    assert "ml_score" in result.component_scores
    assert "signal_count" in result.component_scores
    assert "severity" in result.component_scores
    assert "source_authority" in result.component_scores
    assert result.component_scores["ml_score"] == 0.7
    assert result.component_scores["signal_count"] == 2 / 5.0
    assert result.component_scores["severity"] == 0.75  # high
    assert result.component_scores["source_authority"] == 0.85  # gao


def test_signal_count_capped_at_five():
    """Signal count above 5 should be capped."""
    result = compute_escalation_priority(
        event=_make_event(),
        ml_score=0.5,
        escalation_signal_count=10,
        escalation_severity="medium",
        source_type="oig",
    )
    assert result.component_scores["signal_count"] == 1.0  # min(10,5)/5


def test_unknown_source_type_defaults():
    """Unknown source type should get default weight of 0.30."""
    result = compute_escalation_priority(
        event=_make_event(),
        ml_score=0.5,
        escalation_signal_count=1,
        escalation_severity="medium",
        source_type="unknown_source",
    )
    assert result.component_scores["source_authority"] == 0.30


def test_priority_level_ranges():
    """Verify priority level mapping for different score ranges."""
    # Force a high score
    high = compute_escalation_priority(
        event=_make_event(),
        ml_score=1.0,
        escalation_signal_count=5,
        escalation_severity="critical",
        source_type="oig",
    )
    assert high.priority_level == "critical"

    # Force a low score
    low = compute_escalation_priority(
        event=_make_event(),
        ml_score=0.0,
        escalation_signal_count=0,
        escalation_severity="none",
        source_type="trade_press",
    )
    assert low.priority_level == "low"
