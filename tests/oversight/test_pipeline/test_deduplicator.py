"""Tests for deduplicator module."""

import pytest

from src.oversight.pipeline.deduplicator import (
    extract_entities,
    find_canonical_event,
    link_related_coverage,
    DeduplicationResult,
)
from src.oversight.db_helpers import insert_om_event, get_om_event


def test_extract_entities_gao_report():
    """Extract GAO report number from content."""
    entities = extract_entities(
        title="GAO Report GAO-26-123456 on VA Healthcare",
        content="In report GAO-26-123456, the Government Accountability Office found...",
        url="https://www.gao.gov/products/gao-26-123456",
    )

    assert "gao_report" in entities
    assert entities["gao_report"] == "GAO-26-123456"


def test_extract_entities_bill():
    """Extract bill number from content."""
    entities = extract_entities(
        title="H.R. 1234 - Veterans Healthcare Act",
        content="The House passed H.R. 1234, the Veterans Healthcare Act...",
        url="https://congress.gov/bill/119th-congress/house-bill/1234",
    )

    assert "bill" in entities
    assert "hr1234" in entities["bill"].lower()


def test_extract_entities_cafc_case():
    """Extract CAFC case number from content."""
    entities = extract_entities(
        title="Smith v. McDonough Appeal Decision",
        content="In case No. 2024-1234, the Court of Appeals for the Federal Circuit ruled...",
        url="https://cafc.uscourts.gov/opinions/2024-1234",
    )

    assert "cafc_case" in entities
    assert "2024-1234" in entities["cafc_case"]


def test_extract_entities_oig_report():
    """Extract OIG report number from content."""
    entities = extract_entities(
        title="VA OIG Report 22-01234-567",
        content="The VA Office of Inspector General report 22-01234-567 examines...",
        url="https://www.va.gov/oig/reports/22-01234-567",
    )

    assert "oig_report" in entities


def test_find_canonical_event_match():
    """Find existing canonical event by entity match."""
    # Insert a canonical event
    insert_om_event({
        "event_id": "canonical-gao-123",
        "event_type": "report_release",
        "theme": "healthcare",
        "primary_source_type": "gao",
        "primary_url": "https://gao.gov/products/gao-26-555555",
        "pub_timestamp": "2026-01-20T10:00:00Z",
        "pub_precision": "datetime",
        "pub_source": "extracted",
        "title": "Original GAO Report",
        "canonical_refs": {"gao_report": "GAO-26-555555"},
        "fetched_at": "2026-01-20T12:00:00Z",
    })

    # Try to find it with matching entity
    result = find_canonical_event(
        entities={"gao_report": "GAO-26-555555"},
        source_type="news_wire",
    )

    assert result is not None
    assert result["event_id"] == "canonical-gao-123"


def test_find_canonical_event_no_match():
    """Return None when no matching canonical event."""
    result = find_canonical_event(
        entities={"gao_report": "GAO-26-999999"},
        source_type="news_wire",
    )

    assert result is None


def test_link_related_coverage():
    """Link news coverage to canonical event."""
    # Insert canonical event
    insert_om_event({
        "event_id": "canonical-for-linking",
        "event_type": "report_release",
        "primary_source_type": "gao",
        "primary_url": "https://gao.gov/test",
        "pub_timestamp": "2026-01-20T10:00:00Z",
        "pub_precision": "datetime",
        "pub_source": "extracted",
        "title": "GAO Report for Linking Test",
        "fetched_at": "2026-01-20T12:00:00Z",
    })

    # Link related coverage
    link_related_coverage(
        event_id="canonical-for-linking",
        source_type="news_wire",
        url="https://example.com/news/gao-report",
        title="News coverage of GAO report",
        pub_timestamp="2026-01-20T14:00:00Z",
    )

    # Verify link was created (check via direct DB query if needed)
    # For now just verify no exception was raised


def test_deduplication_result():
    """Test DeduplicationResult dataclass."""
    result = DeduplicationResult(
        is_duplicate=True,
        canonical_event_id="existing-123",
        action="link_coverage",
    )

    assert result.is_duplicate is True
    assert result.canonical_event_id == "existing-123"
