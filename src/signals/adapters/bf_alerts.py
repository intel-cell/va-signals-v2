"""Battlefield gate alerts adapter - transforms gate alerts to normalized envelopes."""

from src.signals.envelope import Envelope

# Alert type → severity mapping
ALERT_TYPE_SEVERITY = {
    "new_gate": "medium",
    "gate_moved": "high",
    "gate_passed": "low",
    "status_changed": "high",
}

# Source type → authority source mapping
GATE_SOURCE_MAP = {
    "hearing_updates": "congress_gov",
    "hearings": "congress_gov",
    "bill_actions": "congress_gov",
    "om_events": "govinfo",
    "bf_calendar_events": "govinfo",
}

# Alert type → authority type mapping
ALERT_TYPE_AUTHORITY = {
    "new_gate": "hearing_notice",
    "gate_moved": "hearing_notice",
    "gate_passed": "report",
    "status_changed": "report",
}

# Topic keywords for battlefield alerts
BATTLEFIELD_TOPIC_KEYWORDS = {
    "disability_benefits": ["disability", "benefits", "compensation"],
    "rating": ["rating", "vasrd", "schedule for rating"],
    "claims_backlog": ["backlog", "processing", "wait time"],
    "appeals": ["appeal", "bva", "board of veterans"],
    "hearing": ["hearing", "testimony", "committee"],
    "legislation": ["bill", "act", "law", "passed", "enacted"],
    "oversight": ["oversight", "investigation", "inspector general", "gao"],
    "rule": ["rule", "regulation", "federal register", "effective date"],
}


class BattlefieldAlertsAdapter:
    """Adapts battlefield gate alerts to normalized envelopes."""

    def adapt(self, alert: dict, version: int = 1) -> Envelope:
        """Transform a gate alert dict to a normalized envelope.

        Args:
            alert: Gate alert dict from create_gate_alert() or get_recent_alerts().
            version: Envelope version.

        Returns:
            Normalized Envelope for the signals ecosystem.
        """
        alert_id = alert.get("alert_id", "")
        alert_type = alert.get("alert_type", "new_gate")
        source_type = alert.get("source_type", "")
        vehicle_id = alert.get("vehicle_id", "")

        # Build body text from available fields
        body_parts = []
        title = alert.get("title") or alert.get("new_value") or f"Gate alert: {alert_type}"
        if alert.get("recommended_action"):
            body_parts.append(f"Action: {alert['recommended_action']}")
        if alert.get("old_value") and alert.get("new_value"):
            body_parts.append(f"Change: {alert['old_value']} → {alert['new_value']}")
        elif alert.get("new_value"):
            body_parts.append(alert["new_value"])
        if alert.get("days_impact") is not None:
            days = alert["days_impact"]
            direction = "delayed" if days > 0 else "accelerated"
            body_parts.append(f"Timeline impact: {abs(days)} days {direction}")
        body_text = "\n".join(body_parts) if body_parts else title

        # Extract topics
        topics = self._extract_topics(title, body_text)

        return Envelope(
            event_id=f"bf-{alert_id}",
            authority_id=alert_id,
            authority_source=GATE_SOURCE_MAP.get(source_type, "govinfo"),
            authority_type=ALERT_TYPE_AUTHORITY.get(alert_type, "report"),
            title=title,
            body_text=body_text,
            topics=topics,
            version=version,
            published_at=alert.get("timestamp"),
            published_at_source="authority",
            metadata={
                "alert_type": alert_type,
                "days_impact": alert.get("days_impact"),
                "vehicle_id": vehicle_id,
                "source_type": source_type,
                "severity": ALERT_TYPE_SEVERITY.get(alert_type, "medium"),
            },
        )

    def _extract_topics(self, title: str, body_text: str) -> list[str]:
        """Extract topics from alert content."""
        combined = f"{title} {body_text}".lower()
        topics = []
        for topic, keywords in BATTLEFIELD_TOPIC_KEYWORDS.items():
            if any(kw in combined for kw in keywords):
                topics.append(topic)
        return topics
