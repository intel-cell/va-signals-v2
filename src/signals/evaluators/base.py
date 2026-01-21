"""Base class for evaluators."""

from abc import ABC, abstractmethod
from typing import Any

from src.signals.envelope import Envelope


# Field access policy
ALLOWED_TOP_LEVEL_FIELDS = {
    "event_id", "authority_id", "authority_source", "authority_type",
    "committee", "subcommittee", "topics", "title", "body_text",
    "content_hash", "version", "published_at", "published_at_source",
    "event_start_at", "source_url", "fetched_at",
}
ALLOWED_NESTED_PREFIX = "metadata."


def get_field_value(envelope: Envelope, field: str) -> Any:
    """Get field value from envelope, respecting access policy."""
    if field in ALLOWED_TOP_LEVEL_FIELDS:
        return getattr(envelope, field, None)
    elif field.startswith(ALLOWED_NESTED_PREFIX):
        # Nested field access: metadata.status -> envelope.metadata["status"]
        parts = field.split(".", 1)
        if len(parts) == 2 and parts[0] == "metadata":
            return envelope.metadata.get(parts[1])
    raise ValueError(f"Field '{field}' not in allowed fields")


class Evaluator(ABC):
    """Base class for all evaluators."""

    name: str = "base"

    @abstractmethod
    def evaluate(self, envelope: Envelope, **args) -> dict:
        """
        Evaluate the envelope against the condition.

        Returns:
            {
                "passed": bool,
                "evidence": { ... evaluator-specific evidence ... }
            }
        """
        pass
