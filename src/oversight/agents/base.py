"""Base class for Oversight Monitor source agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawEvent:
    """Raw event fetched from a source."""

    url: str
    title: str
    raw_html: str
    fetched_at: str
    excerpt: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class TimestampResult:
    """Result of timestamp extraction."""

    pub_timestamp: str | None
    pub_precision: str  # datetime, date, month, unknown
    pub_source: str  # extracted, inferred, missing
    event_timestamp: str | None = None
    event_precision: str | None = None
    event_source: str | None = None


class OversightAgent(ABC):
    """Abstract base class for all oversight source agents."""

    source_type: str = "unknown"

    @abstractmethod
    def fetch_new(self, since: datetime | None) -> list[RawEvent]:
        """
        Fetch events since last run.

        Args:
            since: Datetime of last successful fetch, or None for first run

        Returns:
            List of raw events
        """
        pass

    @abstractmethod
    def backfill(self, start: datetime, end: datetime) -> list[RawEvent]:
        """
        Historical fetch for bootstrap.

        Args:
            start: Start of backfill window
            end: End of backfill window

        Returns:
            List of raw events
        """
        pass

    @abstractmethod
    def extract_timestamps(self, raw: RawEvent) -> TimestampResult:
        """
        Source-specific timestamp extraction.

        Args:
            raw: Raw event to extract timestamps from

        Returns:
            Timestamp extraction result
        """
        pass

    def extract_canonical_refs(self, raw: RawEvent) -> dict:
        """
        Extract identifiers for deduplication.

        Override in subclasses for source-specific extraction.

        Args:
            raw: Raw event

        Returns:
            Dict of canonical references (fr_doc, bill, case, etc.)
        """
        return {}
