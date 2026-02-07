"""Normalized event envelope for signals routing."""

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


def normalize_text(text: str) -> str:
    """Normalize text for matching: lowercase, NFKC, collapse whitespace."""
    if not text:
        return ""
    # NFKC normalization
    text = unicodedata.normalize("NFKC", text)
    # Lowercase
    text = text.lower()
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_content_hash(title: str, body_text: str) -> str:
    """Compute SHA256 hash of normalized content."""
    normalized = normalize_text(f"{title} {body_text}")
    hash_bytes = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{hash_bytes}"


@dataclass
class Envelope:
    """Normalized event envelope consumed by the signals router."""

    # Identity
    event_id: str
    authority_id: str

    # Authority
    authority_source: str  # govinfo | congress_gov | house_veterans | senate_veterans
    authority_type: str  # hearing_notice | bill_text | rule | report | press_release

    # Content
    title: str
    body_text: str

    # Classification hints (optional)
    committee: str | None = None  # HVAC | SVAC | null
    subcommittee: str | None = None
    topics: list[str] = field(default_factory=list)

    # Change detection
    content_hash: str | None = None
    version: int = 1

    # Temporal
    published_at: str | None = None
    published_at_source: str = "derived"  # authority | derived
    event_start_at: str | None = None

    # Provenance
    source_url: str | None = None
    fetched_at: str | None = None

    # Structured metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Compute content_hash if not provided."""
        if self.content_hash is None:
            self.content_hash = compute_content_hash(self.title, self.body_text)
