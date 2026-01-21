"""OM Events adapter - transforms oversight monitor events to normalized envelopes."""

from typing import Optional

from src.signals.envelope import Envelope


# Source type to authority source mapping
SOURCE_TYPE_MAP = {
    "gao": "govinfo",
    "oig": "govinfo",
    "crs": "congress_gov",
    "congressional_record": "congress_gov",
    "committee_press": "congress_gov",
    "news_wire": "news",
    "investigative": "news",
    "trade_press": "news",
    "cafc": "govinfo",
}

# Event type to authority type mapping
EVENT_TYPE_MAP = {
    "report": "report",
    "hearing": "hearing_notice",
    "testimony": "hearing_notice",
    "press_release": "press_release",
    "rule": "rule",
    "news": "press_release",
}


class OMEventsAdapter:
    """Adapts oversight monitor events to normalized envelopes."""

    def adapt(self, event: dict, version: int = 1) -> Envelope:
        """Transform an OM event record to a normalized envelope."""
        event_id = event.get("event_id", "")
        source_type = event.get("primary_source_type", "")
        event_type = event.get("event_type", "")

        # Build body text
        body_parts = []
        if event.get("title"):
            body_parts.append(event["title"])
        if event.get("summary"):
            body_parts.append(event["summary"])
        body_text = "\n".join(body_parts) if body_parts else event.get("raw_content", "")[:1000]

        # Extract topics from title, summary, and theme
        topics = self._extract_topics(
            event.get("title", ""),
            event.get("summary", ""),
            event.get("theme", "")
        )

        return Envelope(
            event_id=f"om-{event_id}",
            authority_id=event_id,
            authority_source=SOURCE_TYPE_MAP.get(source_type, "govinfo"),
            authority_type=EVENT_TYPE_MAP.get(event_type, "report"),
            title=event.get("title", ""),
            body_text=body_text,
            topics=topics,
            version=version,
            published_at=event.get("pub_timestamp"),
            published_at_source="authority" if event.get("pub_precision") == "day" else "derived",
            event_start_at=event.get("event_timestamp"),
            source_url=event.get("primary_url"),
            fetched_at=event.get("fetched_at"),
            metadata={
                "theme": event.get("theme"),
                "primary_source_type": source_type,
                "is_escalation": event.get("is_escalation"),
                "escalation_signals": event.get("escalation_signals"),
                "is_deviation": event.get("is_deviation"),
                "deviation_reason": event.get("deviation_reason"),
            },
        )

    def _extract_topics(self, title: str, summary: str, theme: str) -> list[str]:
        """Extract topics from content and theme."""
        combined = f"{title} {summary} {theme}".lower()
        topics = []

        topic_keywords = {
            "disability_benefits": ["disability", "benefits", "compensation", "veteran benefits"],
            "rating": ["rating", "vasrd", "schedule for rating"],
            "exam_quality": ["exam", "c&p", "medical examination", "contractor exam"],
            "claims_backlog": ["backlog", "processing", "wait time"],
            "appeals": ["appeal", "bva", "board of veterans"],
        }

        for topic, keywords in topic_keywords.items():
            if any(kw in combined for kw in keywords):
                topics.append(topic)

        return topics
