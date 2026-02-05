"""
BRAVO-ALPHA Integration Module

Provides bridge functions for ALPHA COMMAND (CEO Brief) to consume
BRAVO COMMAND (Evidence Pack) citations.

Integration Points:
- Convert EvidenceSource to ALPHA's SourceCitation format
- Lookup evidence sources for CEO Brief enrichment
- Validate citations against evidence database
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from src.db import connect, execute
from src.evidence.models import EvidenceSource, SourceType as BravoSourceType


# ALPHA's SourceType enum values (mirror for compatibility)
class AlphaSourceType:
    FEDERAL_REGISTER = "federal_register"
    BILL = "bill"
    HEARING = "hearing"
    OVERSIGHT = "oversight"
    STATE = "state"
    ECFR = "ecfr"
    GAO = "gao"
    OIG = "oig"
    CRS = "crs"
    NEWS = "news"


# Mapping from BRAVO source types to ALPHA source types
BRAVO_TO_ALPHA_SOURCE_TYPE = {
    BravoSourceType.FEDERAL_REGISTER: AlphaSourceType.FEDERAL_REGISTER,
    BravoSourceType.BILL: AlphaSourceType.BILL,
    BravoSourceType.HEARING: AlphaSourceType.HEARING,
    BravoSourceType.GAO_REPORT: AlphaSourceType.GAO,
    BravoSourceType.OIG_REPORT: AlphaSourceType.OIG,
    BravoSourceType.CRS_REPORT: AlphaSourceType.CRS,
    BravoSourceType.VA_GUIDANCE: AlphaSourceType.OVERSIGHT,
    BravoSourceType.AUTHORITY_DOC: AlphaSourceType.OVERSIGHT,
    BravoSourceType.ECFR: AlphaSourceType.ECFR,
    BravoSourceType.NEWS: AlphaSourceType.NEWS,
}


@dataclass
class SourceCitationForAlpha:
    """
    ALPHA-compatible citation format.

    This matches ALPHA's SourceCitation dataclass exactly.
    """
    source_type: str  # AlphaSourceType value
    source_id: str
    title: str
    url: str
    date: date
    excerpt: Optional[str] = None
    section_ref: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "date": self.date.isoformat() if self.date else None,
            "excerpt": self.excerpt,
            "section_ref": self.section_ref,
        }


def evidence_source_to_alpha_citation(
    source: EvidenceSource,
    excerpt: Optional[str] = None,
    section_ref: Optional[str] = None,
) -> SourceCitationForAlpha:
    """
    Convert BRAVO EvidenceSource to ALPHA SourceCitation format.

    Args:
        source: BRAVO EvidenceSource object
        excerpt: Optional text excerpt to include
        section_ref: Optional section reference

    Returns:
        SourceCitationForAlpha compatible with ALPHA's schema
    """
    # Map source type
    alpha_type = BRAVO_TO_ALPHA_SOURCE_TYPE.get(
        source.source_type,
        AlphaSourceType.OVERSIGHT  # Default fallback
    )

    # Parse date from ISO string
    pub_date = None
    if source.date_published:
        try:
            # Handle various date formats
            date_str = source.date_published.split("T")[0]  # Remove time if present
            pub_date = date.fromisoformat(date_str)
        except (ValueError, AttributeError):
            pub_date = date.today()
    else:
        pub_date = date.today()

    # Determine source_id for ALPHA (use identifier not hash)
    source_id = (
        source.fr_doc_number or
        source.bill_number or
        source.report_number or
        source.source_id[:12]  # Fallback to truncated hash
    )

    return SourceCitationForAlpha(
        source_type=alpha_type,
        source_id=source_id,
        title=source.title,
        url=source.url,
        date=pub_date,
        excerpt=excerpt,
        section_ref=section_ref,
    )


def find_evidence_for_source(
    source_type: str,
    source_id: str,
) -> Optional[SourceCitationForAlpha]:
    """
    Find evidence pack citation for a source.

    This is the primary ALPHA integration function. ALPHA calls this
    to enrich CEO Brief citations with BRAVO evidence.

    Args:
        source_type: ALPHA source type (federal_register, bill, gao, etc.)
        source_id: Source identifier (FR doc number, bill_id, report number)

    Returns:
        SourceCitationForAlpha if found, None otherwise
    """
    con = connect()
    try:
        # Search by various identifier fields
        cur = execute(
            con,
            """
            SELECT source_id, source_type, title, url, date_published,
                   fr_doc_number, bill_number, report_number
            FROM evidence_sources
            WHERE fr_doc_number = :source_id
               OR bill_number = :source_id
               OR report_number = :source_id
               OR source_id LIKE :source_id_pattern
            LIMIT 1
            """,
            {
                "source_id": source_id,
                "source_id_pattern": f"{source_id}%",
            }
        )
        row = cur.fetchone()

        if not row:
            return None

        (db_source_id, db_source_type, title, url, date_published,
         fr_doc_number, bill_number, report_number) = row

        # Parse date
        pub_date = None
        if date_published:
            try:
                date_str = date_published.split("T")[0]
                pub_date = date.fromisoformat(date_str)
            except (ValueError, AttributeError):
                pub_date = date.today()
        else:
            pub_date = date.today()

        # Determine best source_id to use
        display_source_id = fr_doc_number or bill_number or report_number or source_id

        return SourceCitationForAlpha(
            source_type=source_type,  # Use ALPHA's type as passed in
            source_id=display_source_id,
            title=title,
            url=url,
            date=pub_date,
        )

    finally:
        con.close()


def get_citations_for_brief(
    topic_keywords: list[str],
    limit: int = 10,
) -> list[SourceCitationForAlpha]:
    """
    Get citations relevant to CEO Brief topics.

    Args:
        topic_keywords: Keywords to search for
        limit: Maximum citations to return

    Returns:
        List of SourceCitationForAlpha objects
    """
    from src.evidence.extractors import search_citations_by_keyword

    citations = []
    seen_ids = set()

    for keyword in topic_keywords:
        sources = search_citations_by_keyword(keyword, limit=limit)
        for source in sources:
            if source.source_id not in seen_ids:
                seen_ids.add(source.source_id)
                citations.append(evidence_source_to_alpha_citation(source))

            if len(citations) >= limit:
                break

        if len(citations) >= limit:
            break

    return citations


def validate_brief_citations(
    citations: list[dict],
) -> tuple[bool, list[str]]:
    """
    Validate that CEO Brief citations exist in evidence database.

    Args:
        citations: List of citation dicts from CEO Brief

    Returns:
        Tuple of (all_valid, list of error messages)
    """
    errors = []
    con = connect()

    try:
        for i, citation in enumerate(citations):
            source_id = citation.get("source_id")
            if not source_id:
                errors.append(f"Citation {i+1}: Missing source_id")
                continue

            # Check if source exists
            cur = execute(
                con,
                """
                SELECT 1 FROM evidence_sources
                WHERE fr_doc_number = :source_id
                   OR bill_number = :source_id
                   OR report_number = :source_id
                   OR source_id LIKE :source_id_pattern
                LIMIT 1
                """,
                {
                    "source_id": source_id,
                    "source_id_pattern": f"{source_id}%",
                }
            )

            if not cur.fetchone():
                errors.append(f"Citation {i+1}: Source '{source_id}' not found in evidence database")

    finally:
        con.close()

    return (len(errors) == 0, errors)


def enrich_brief_with_evidence(
    brief_sources: list[dict],
) -> list[dict]:
    """
    Enrich CEO Brief sources with additional evidence metadata.

    Takes existing brief sources and adds BRAVO evidence pack data
    where available.

    Args:
        brief_sources: List of source dicts from CEO Brief

    Returns:
        Enriched list of source dicts
    """
    enriched = []

    for source in brief_sources:
        source_id = source.get("source_id")
        source_type = source.get("source_type", "oversight")

        # Try to find in evidence database
        evidence = find_evidence_for_source(source_type, source_id)

        if evidence:
            # Merge evidence data
            enriched_source = {
                **source,
                "evidence_verified": True,
                "evidence_title": evidence.title,
                "evidence_url": evidence.url,
                "evidence_date": evidence.date.isoformat() if evidence.date else None,
            }
        else:
            enriched_source = {
                **source,
                "evidence_verified": False,
            }

        enriched.append(enriched_source)

    return enriched


# Convenience exports for ALPHA
__all__ = [
    "SourceCitationForAlpha",
    "evidence_source_to_alpha_citation",
    "find_evidence_for_source",
    "get_citations_for_brief",
    "validate_brief_citations",
    "enrich_brief_with_evidence",
]
