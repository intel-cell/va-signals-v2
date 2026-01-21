"""Hearings adapter - transforms hearing records to normalized envelopes."""

from typing import Optional

from src.signals.envelope import Envelope


# Committee code to standard committee mapping
COMMITTEE_MAP = {
    "HSVA": "HVAC",
    "SSVA": "SVAC",
}

# Committee code to authority source mapping
AUTHORITY_SOURCE_MAP = {
    "HSVA": "house_veterans",
    "SSVA": "senate_veterans",
}


class HearingsAdapter:
    """Adapts hearing records to normalized envelopes."""

    def adapt(self, hearing: dict, version: int = 1) -> Envelope:
        """Transform a hearing record to a normalized envelope."""
        event_id = hearing.get("event_id", "")
        committee_code = hearing.get("committee_code", "")

        # Map committee
        committee = COMMITTEE_MAP.get(committee_code)
        authority_source = AUTHORITY_SOURCE_MAP.get(committee_code, "congress_gov")

        # Build body text from available fields
        body_parts = []
        if hearing.get("title"):
            body_parts.append(hearing["title"])
        if hearing.get("committee_name"):
            body_parts.append(f"Committee: {hearing['committee_name']}")
        if hearing.get("location"):
            body_parts.append(f"Location: {hearing['location']}")
        body_text = "\n".join(body_parts)

        # Determine topics based on title keywords
        topics = self._extract_topics(hearing.get("title", ""))

        return Envelope(
            event_id=f"hearing-{event_id}",
            authority_id=event_id,
            authority_source=authority_source,
            authority_type="hearing_notice",
            title=hearing.get("title", ""),
            body_text=body_text,
            committee=committee,
            topics=topics,
            version=version,
            published_at=hearing.get("first_seen_at"),
            published_at_source="derived",
            event_start_at=self._build_event_time(hearing),
            source_url=hearing.get("url"),
            fetched_at=hearing.get("updated_at"),
            metadata={
                "status": hearing.get("status"),
                "meeting_type": hearing.get("meeting_type"),
                "chamber": hearing.get("chamber"),
                "congress": hearing.get("congress"),
            },
        )

    def _extract_topics(self, title: str) -> list[str]:
        """Extract topics from title keywords."""
        title_lower = title.lower()
        topics = []

        topic_keywords = {
            "disability_benefits": ["disability", "benefits", "claims"],
            "rating": ["rating", "vasrd", "schedule"],
            "exam_quality": ["exam", "c&p", "medical examination"],
            "claims_backlog": ["backlog", "processing", "wait time"],
            "appeals": ["appeal", "bva", "board"],
        }

        for topic, keywords in topic_keywords.items():
            if any(kw in title_lower for kw in keywords):
                topics.append(topic)

        return topics

    def _build_event_time(self, hearing: dict) -> Optional[str]:
        """Build ISO timestamp from hearing date/time."""
        date = hearing.get("hearing_date")
        time = hearing.get("hearing_time", "00:00")
        if date:
            return f"{date}T{time}:00Z"
        return None
