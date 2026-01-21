"""Deduplicator for oversight events - entity extraction and canonical matching."""

import json
import re
from dataclasses import dataclass
from typing import Optional

from src.db import connect


@dataclass
class DeduplicationResult:
    """Result of deduplication check."""

    is_duplicate: bool
    canonical_event_id: Optional[str] = None
    action: str = "new"  # new, link_coverage, skip


# Entity extraction patterns
GAO_PATTERN = re.compile(r"GAO-(\d{2})-(\d+)", re.IGNORECASE)
OIG_PATTERN = re.compile(r"(\d{2})-(\d{5})-(\d+)", re.IGNORECASE)
BILL_HR_PATTERN = re.compile(r"H\.?R\.?\s*(\d+)", re.IGNORECASE)
BILL_S_PATTERN = re.compile(r"S\.?\s*(\d+)", re.IGNORECASE)
CAFC_PATTERN = re.compile(r"(?:No\.?\s*)?(\d{4})-(\d+)", re.IGNORECASE)
CRS_PATTERN = re.compile(r"(R\d{5}|RL\d{5}|RS\d{5})", re.IGNORECASE)


def extract_entities(title: str, content: str, url: str) -> dict:
    """
    Extract canonical entity identifiers from content.

    Args:
        title: Event title
        content: Event content/excerpt
        url: Event URL

    Returns:
        Dict of entity type -> identifier
    """
    combined = f"{title} {content} {url}"
    entities = {}

    # GAO report number
    gao_match = GAO_PATTERN.search(combined)
    if gao_match:
        year, number = gao_match.groups()
        entities["gao_report"] = f"GAO-{year}-{number}".upper()

    # OIG report number
    oig_match = OIG_PATTERN.search(combined)
    if oig_match:
        entities["oig_report"] = "-".join(oig_match.groups())

    # House bill
    hr_match = BILL_HR_PATTERN.search(combined)
    if hr_match:
        entities["bill"] = f"HR{hr_match.group(1)}"

    # Senate bill
    s_match = BILL_S_PATTERN.search(combined)
    if s_match and "bill" not in entities:  # Don't overwrite HR
        entities["bill"] = f"S{s_match.group(1)}"

    # CAFC case number
    if "cafc" in url.lower() or "federal circuit" in combined.lower():
        cafc_match = CAFC_PATTERN.search(combined)
        if cafc_match:
            entities["cafc_case"] = f"{cafc_match.group(1)}-{cafc_match.group(2)}"

    # CRS report number
    crs_match = CRS_PATTERN.search(combined)
    if crs_match:
        entities["crs_report"] = crs_match.group(1).upper()

    return entities


def find_canonical_event(entities: dict, source_type: str) -> Optional[dict]:
    """
    Find an existing canonical event matching the extracted entities.

    Args:
        entities: Dict of entity type -> identifier
        source_type: Source type of the new event

    Returns:
        Matching canonical event dict or None
    """
    if not entities:
        return None

    con = connect()
    con.row_factory = None

    # Build query to find events with matching canonical_refs
    for entity_type, entity_value in entities.items():
        # Search for events with this entity in canonical_refs JSON
        cur = con.execute(
            """
            SELECT event_id, event_type, theme, primary_source_type, primary_url,
                   title, canonical_refs
            FROM om_events
            WHERE canonical_refs LIKE ?
            LIMIT 1
            """,
            (f'%"{entity_value}"%',),
        )
        row = cur.fetchone()

        if row:
            con.close()
            return {
                "event_id": row[0],
                "event_type": row[1],
                "theme": row[2],
                "primary_source_type": row[3],
                "primary_url": row[4],
                "title": row[5],
                "canonical_refs": json.loads(row[6]) if row[6] else None,
            }

    con.close()
    return None


def link_related_coverage(
    event_id: str,
    source_type: str,
    url: str,
    title: str,
    pub_timestamp: Optional[str] = None,
    pub_precision: str = "unknown",
) -> int:
    """
    Link related coverage to an existing canonical event.

    Args:
        event_id: Canonical event ID to link to
        source_type: Source type of the coverage
        url: URL of the coverage
        title: Title of the coverage
        pub_timestamp: Publication timestamp
        pub_precision: Timestamp precision

    Returns:
        Row ID of the new coverage link
    """
    from datetime import datetime, timezone

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    con = connect()
    cur = con.execute(
        """
        INSERT OR IGNORE INTO om_related_coverage (
            event_id, source_type, url, title, pub_timestamp, pub_precision, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, source_type, url, title, pub_timestamp, pub_precision, fetched_at),
    )
    row_id = cur.lastrowid
    con.commit()
    con.close()

    return row_id


def deduplicate_event(
    title: str,
    content: str,
    url: str,
    source_type: str,
    pub_timestamp: Optional[str] = None,
) -> DeduplicationResult:
    """
    Full deduplication check for an event.

    Args:
        title: Event title
        content: Event content/excerpt
        url: Event URL
        source_type: Source type
        pub_timestamp: Publication timestamp

    Returns:
        DeduplicationResult with action to take
    """
    # Extract entities
    entities = extract_entities(title, content, url)

    if not entities:
        # No entities to match on - treat as new
        return DeduplicationResult(is_duplicate=False, action="new")

    # Find canonical event
    canonical = find_canonical_event(entities, source_type)

    if canonical:
        # Link as related coverage
        link_related_coverage(
            event_id=canonical["event_id"],
            source_type=source_type,
            url=url,
            title=title,
            pub_timestamp=pub_timestamp,
        )
        return DeduplicationResult(
            is_duplicate=True,
            canonical_event_id=canonical["event_id"],
            action="link_coverage",
        )

    # No match - new canonical event
    return DeduplicationResult(is_duplicate=False, action="new")
