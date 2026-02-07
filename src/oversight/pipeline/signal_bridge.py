"""Signal bridge — connects oversight pipeline to signals router and WebSocket.

Routes stored oversight events through:
1. OMEventsAdapter → Envelope
2. SignalsRouter → RouteResults
3. PriorityScorer → PriorityResult
4. WebSocket push (if threshold met)
5. DB surfacing (if alert threshold met)
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Lazy singleton for SignalsRouter (avoids import-time DB/YAML loading)
_router_instance = None
_adapter_instance = None


def _get_router():
    global _router_instance
    if _router_instance is None:
        from src.signals.router import SignalsRouter

        _router_instance = SignalsRouter(categories=["oversight_accountability"])
    return _router_instance


def _get_adapter():
    global _adapter_instance
    if _adapter_instance is None:
        from src.signals.adapters.om_events import OMEventsAdapter

        _adapter_instance = OMEventsAdapter()
    return _adapter_instance


@dataclass
class BridgeResult:
    """Result of routing an oversight event through the signal bridge."""

    event_id: str
    routed: bool = False
    route_count: int = 0
    suppressed_count: int = 0
    priority_score: float = 0.0
    priority_level: str = "low"
    surfaced: bool = False
    websocket_pushed: bool = False
    errors: list[str] = field(default_factory=list)


def route_oversight_event(event: dict) -> BridgeResult:
    """Route a stored oversight event through the signals engine + priority scoring.

    This function is called AFTER the event has been persisted to om_events.
    It is non-fatal — any failure returns a BridgeResult with error details.

    Args:
        event: The om_event dict (must have event_id, title, etc.)

    Returns:
        BridgeResult with routing metadata.
    """
    event_id = event.get("event_id", "unknown")
    result = BridgeResult(event_id=event_id)

    try:
        # 1. Adapt to Envelope
        adapter = _get_adapter()
        envelope = adapter.adapt(event)

        # 2. Route through SignalsRouter
        router = _get_router()
        route_results = router.route(envelope)
        result.route_count = len(route_results)
        result.suppressed_count = sum(1 for r in route_results if r.suppressed)
        result.routed = len(route_results) > 0

        # 3. Compute priority
        from src.oversight.pipeline.priority import compute_escalation_priority

        # Derive escalation_severity from the highest-severity route result
        severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        active_results = [r for r in route_results if not r.suppressed]

        if active_results:
            highest_severity = max(
                active_results,
                key=lambda r: severity_order.get(r.severity, 0),
            ).severity
        else:
            # Fall back to event's own escalation signals
            highest_severity = _extract_severity_from_event(event)

        escalation_signal_count = len(event.get("escalation_signals") or [])

        priority = compute_escalation_priority(
            event=event,
            ml_score=event.get("ml_score"),
            escalation_signal_count=escalation_signal_count,
            escalation_severity=highest_severity,
            source_type=event.get("primary_source_type", "other"),
        )

        result.priority_score = priority.priority_score
        result.priority_level = priority.priority_level

        # 4. WebSocket push if threshold met
        if priority.should_push_websocket and active_results:
            try:
                from src.websocket.broadcast import notify_new_signal_sync

                signal_data = {
                    "type": "oversight_escalation",
                    "event_id": event_id,
                    "title": event.get("title", ""),
                    "source": event.get("primary_source_type", ""),
                    "severity": highest_severity,
                    "priority_score": priority.priority_score,
                    "priority_level": priority.priority_level,
                }
                notify_new_signal_sync(signal_data)
                result.websocket_pushed = True
            except Exception as e:
                result.errors.append(f"WebSocket push failed: {e}")
                logger.warning("WebSocket push failed for %s: %s", event_id, e)

        # 5. Surface in DB if alert threshold met
        if priority.should_alert:
            try:
                from src.oversight.db_helpers import update_om_event_surfaced

                update_om_event_surfaced(event_id, surfaced_via="signal_bridge")
                result.surfaced = True
            except Exception as e:
                result.errors.append(f"DB surfacing failed: {e}")
                logger.warning("DB surfacing failed for %s: %s", event_id, e)

    except Exception as e:
        result.errors.append(f"Bridge error: {e}")
        logger.error("Signal bridge failed for %s: %s", event_id, e)

    return result


def _extract_severity_from_event(event: dict) -> str:
    """Extract the highest severity from an event's escalation signals."""
    signals = event.get("escalation_signals") or []
    if not signals:
        return "none"

    # Escalation signals are string names, not severity levels.
    # Use the event's ml_risk_level as a proxy.
    ml_risk = event.get("ml_risk_level")
    if ml_risk and ml_risk in ("critical", "high", "medium", "low"):
        return ml_risk

    # If we have any escalation signals at all, default to medium
    return "medium" if signals else "none"


def reset_singletons():
    """Reset lazy singletons (for testing)."""
    global _router_instance, _adapter_instance
    _router_instance = None
    _adapter_instance = None
