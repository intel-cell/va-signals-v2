"""Battlefield signal bridge — routes gate alerts through priority scoring and WebSocket push.

Simpler than the oversight signal bridge: gate alerts are already classified
by the detection functions (alert_type, days_impact, recommended_action),
so no YAML routing step is needed. Flow: adapt → prioritize → push.
"""

import logging
from dataclasses import dataclass, field

from src.oversight.pipeline.priority import compute_escalation_priority
from src.signals.adapters.bf_alerts import ALERT_TYPE_SEVERITY

logger = logging.getLogger(__name__)

# Source type → authority source key for priority scoring
GATE_SOURCE_MAP = {
    "hearing_updates": "congressional_record",
    "hearings": "congressional_record",
    "bill_actions": "crs",
    "om_events": "gao",
    "bf_calendar_events": "gao",
}


@dataclass
class GateBridgeResult:
    """Result of routing a gate alert through the signal bridge."""

    alert_id: str = ""
    priority_score: float = 0.0
    priority_level: str = "low"
    websocket_pushed: bool = False
    errors: list[str] = field(default_factory=list)


def route_gate_alert(alert: dict) -> GateBridgeResult:
    """Route a gate alert through priority scoring and WebSocket push.

    Args:
        alert: Gate alert dict with keys: alert_id, vehicle_id, alert_type,
               title, new_value, old_value, days_impact, recommended_action,
               source_type, source_event_id.

    Returns:
        GateBridgeResult with priority score and push status.
    """
    result = GateBridgeResult(alert_id=alert.get("alert_id", ""))
    alert_type = alert.get("alert_type", "new_gate")
    source_type = alert.get("source_type", "")
    days_impact = alert.get("days_impact")

    # Determine escalation severity from alert type
    severity = ALERT_TYPE_SEVERITY.get(alert_type, "medium")

    # Negative days_impact (acceleration) bumps severity to critical
    if days_impact is not None and days_impact < 0:
        severity = "critical"

    # Determine escalation signal count
    escalation_types = {"gate_moved", "status_changed"}
    signal_count = 1 if alert_type in escalation_types else 0

    # Compute priority
    try:
        priority = compute_escalation_priority(
            event=alert,
            ml_score=None,
            escalation_signal_count=signal_count,
            escalation_severity=severity,
            source_type=GATE_SOURCE_MAP.get(source_type, "other"),
        )
        result.priority_score = priority.priority_score
        result.priority_level = priority.priority_level

        # Push via WebSocket if above threshold
        if priority.should_push_websocket:
            try:
                _push_websocket(alert, result)
                result.websocket_pushed = True
            except Exception as e:
                logger.warning(f"WebSocket push failed (non-fatal): {e}")
                result.errors.append(f"websocket: {e}")

    except Exception as e:
        logger.warning(f"Priority scoring failed (non-fatal): {e}")
        result.errors.append(f"priority: {e}")

    return result


def _push_websocket(alert: dict, bridge_result: GateBridgeResult) -> None:
    """Push gate alert via WebSocket broadcast."""
    import asyncio

    from src.websocket.broadcast import notify_battlefield_update, notify_new_signal_sync

    signal_data = {
        "type": "battlefield_gate",
        "alert_type": alert.get("alert_type"),
        "title": alert.get("title") or alert.get("new_value", ""),
        "vehicle_id": alert.get("vehicle_id"),
        "days_impact": alert.get("days_impact"),
        "priority_level": bridge_result.priority_level,
        "priority_score": bridge_result.priority_score,
        "recommended_action": alert.get("recommended_action"),
        "source_type": alert.get("source_type"),
    }

    # Push to signals subscribers
    notify_new_signal_sync(signal_data)

    # Push to battlefield-topic subscribers
    battlefield_data = {
        "alert_type": alert.get("alert_type"),
        "title": alert.get("title") or alert.get("new_value", ""),
        "vehicle_id": alert.get("vehicle_id"),
        "days_impact": alert.get("days_impact"),
        "priority_level": bridge_result.priority_level,
    }
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(notify_battlefield_update(battlefield_data))
        else:
            loop.run_until_complete(notify_battlefield_update(battlefield_data))
    except RuntimeError:
        asyncio.run(notify_battlefield_update(battlefield_data))
