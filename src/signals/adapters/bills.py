"""Bills adapter - transforms bill records to normalized envelopes."""

from src.signals.envelope import Envelope


class BillsAdapter:
    """Adapts bill records to normalized envelopes."""

    def adapt(self, bill: dict, version: int = 1) -> Envelope:
        """Transform a bill record to a normalized envelope."""
        bill_id = bill.get("bill_id", "")

        # Build body text
        body_parts = []
        if bill.get("title"):
            body_parts.append(bill["title"])
        if bill.get("latest_action_text"):
            body_parts.append(f"Latest action: {bill['latest_action_text']}")
        if bill.get("policy_area"):
            body_parts.append(f"Policy area: {bill['policy_area']}")
        body_text = "\n".join(body_parts)

        # Extract topics from title and policy area
        topics = self._extract_topics(bill.get("title", ""), bill.get("policy_area", ""))

        return Envelope(
            event_id=f"bill-{bill_id}",
            authority_id=bill_id,
            authority_source="congress_gov",
            authority_type="bill_text",
            title=bill.get("title", ""),
            body_text=body_text,
            committee=self._get_committee_from_committees(bill.get("committees_json")),
            topics=topics,
            version=version,
            published_at=bill.get("introduced_date"),
            published_at_source="authority",
            source_url=f"https://congress.gov/bill/{bill.get('congress', '')}/{bill.get('bill_type', '').lower()}/{bill.get('bill_number', '')}",
            fetched_at=bill.get("updated_at"),
            metadata={
                "congress": bill.get("congress"),
                "bill_type": bill.get("bill_type"),
                "bill_number": bill.get("bill_number"),
                "sponsor_name": bill.get("sponsor_name"),
                "sponsor_party": bill.get("sponsor_party"),
                "cosponsors_count": bill.get("cosponsors_count"),
                "latest_action_date": bill.get("latest_action_date"),
            },
        )

    def _extract_topics(self, title: str, policy_area: str) -> list[str]:
        """Extract topics from title and policy area."""
        combined = f"{title} {policy_area}".lower()
        topics = []

        topic_keywords = {
            "disability_benefits": ["disability", "benefits", "compensation"],
            "rating": ["rating", "vasrd", "schedule for rating"],
            "exam_quality": ["exam", "c&p", "medical examination"],
            "claims_backlog": ["backlog", "processing", "wait time", "claims processing"],
            "appeals": ["appeal", "bva", "board of veterans"],
            "vasrd": ["vasrd", "schedule for rating disabilities"],
        }

        for topic, keywords in topic_keywords.items():
            if any(kw in combined for kw in keywords):
                topics.append(topic)

        return topics

    def _get_committee_from_committees(self, committees_json: str | None) -> str | None:
        """Extract VA committee from committees JSON if present."""
        if not committees_json:
            return None
        # committees_json is a JSON string; look for HVAC or SVAC patterns
        if "Veterans" in committees_json and "House" in committees_json:
            return "HVAC"
        if "Veterans" in committees_json and "Senate" in committees_json:
            return "SVAC"
        return None
