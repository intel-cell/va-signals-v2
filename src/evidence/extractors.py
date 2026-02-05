"""Citation extractors for each source type.

Extractors query the database and build EvidenceSource objects with proper
citations, dates, and provenance information.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Optional

from src.db import connect, execute
from src.evidence.models import (
    EvidenceSource,
    EvidenceExcerpt,
    SourceType,
)


def utc_now_iso() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# FEDERAL REGISTER EXTRACTOR
# =============================================================================

FR_CITATION_PATTERN = re.compile(r"(\d{2})\s*FR\s*(\d+)", re.IGNORECASE)
FR_EFFECTIVE_DATE_PATTERN = re.compile(
    r"(?:effective\s+(?:date|on)?:?\s*)(\w+\s+\d{1,2},?\s+\d{4})",
    re.IGNORECASE
)
FR_COMMENT_DEADLINE_PATTERN = re.compile(
    r"(?:comment[s]?\s+(?:must\s+be\s+)?(?:received\s+)?(?:by|deadline):?\s*)(\w+\s+\d{1,2},?\s+\d{4})",
    re.IGNORECASE
)


def extract_fr_citation(doc_number: str) -> Optional[EvidenceSource]:
    """
    Extract Federal Register citation from a document.

    Args:
        doc_number: FR document number (e.g., "2024-01234")

    Returns:
        EvidenceSource with FR citation details or None if not found
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT doc_id, published_date, source_url
            FROM fr_seen
            WHERE doc_id = :doc_id
            """,
            {"doc_id": doc_number}
        )
        row = cur.fetchone()

        if not row:
            return None

        doc_id, published_date, source_url = row

        # Get summary if available
        cur = execute(
            con,
            """
            SELECT summary, bullet_points, veteran_impact
            FROM fr_summaries
            WHERE doc_id = :doc_id
            """,
            {"doc_id": doc_number}
        )
        summary_row = cur.fetchone()

        # Build FR citation
        # Note: FR citation format is "XX FR XXXXX" but we don't have volume/page
        # so we use the document number as the primary identifier
        fr_citation = f"FR Doc. {doc_number}"

        metadata = {}
        if summary_row:
            metadata["summary"] = summary_row[0]
            metadata["bullet_points"] = summary_row[1]
            metadata["veteran_impact"] = summary_row[2]

        source_id = EvidenceSource.generate_source_id(
            SourceType.FEDERAL_REGISTER,
            doc_number
        )

        return EvidenceSource(
            source_id=source_id,
            source_type=SourceType.FEDERAL_REGISTER,
            title=f"Federal Register Document {doc_number}",
            url=source_url,
            date_published=published_date,
            date_accessed=utc_now_iso(),
            fr_doc_number=doc_number,
            fr_citation=fr_citation,
            issuing_agency="Federal Register",
            document_type="notice",
            metadata=metadata,
        )
    finally:
        con.close()


def extract_fr_citations_by_date(start_date: str, end_date: str) -> list[EvidenceSource]:
    """
    Extract all FR citations within a date range.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        List of EvidenceSource objects
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT doc_id, published_date, source_url
            FROM fr_seen
            WHERE published_date >= :start_date AND published_date <= :end_date
            ORDER BY published_date DESC
            """,
            {"start_date": start_date, "end_date": end_date}
        )

        sources = []
        for row in cur.fetchall():
            doc_id, published_date, source_url = row
            source_id = EvidenceSource.generate_source_id(
                SourceType.FEDERAL_REGISTER,
                doc_id
            )
            sources.append(EvidenceSource(
                source_id=source_id,
                source_type=SourceType.FEDERAL_REGISTER,
                title=f"Federal Register Document {doc_id}",
                url=source_url,
                date_published=published_date,
                date_accessed=utc_now_iso(),
                fr_doc_number=doc_id,
                fr_citation=f"FR Doc. {doc_id}",
                issuing_agency="Federal Register",
            ))

        return sources
    finally:
        con.close()


def extract_fr_effective_date(text: str) -> Optional[str]:
    """Extract effective date from FR document text."""
    match = FR_EFFECTIVE_DATE_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def extract_fr_comment_deadline(text: str) -> Optional[str]:
    """Extract comment deadline from FR document text."""
    match = FR_COMMENT_DEADLINE_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


# =============================================================================
# BILL/AMENDMENT EXTRACTOR
# =============================================================================

BILL_SECTION_PATTERN = re.compile(
    r"(?:SEC(?:TION)?\.?\s*)?(\d+)\s*[.\(]\s*([a-z])\s*[.\)]",
    re.IGNORECASE
)


def extract_bill_citation(bill_id: str) -> Optional[EvidenceSource]:
    """
    Extract bill citation from database.

    Args:
        bill_id: Bill identifier (e.g., "118-hr-5")

    Returns:
        EvidenceSource with bill details or None if not found
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT
                bill_id, congress, bill_type, bill_number, title,
                sponsor_name, sponsor_party, sponsor_state,
                introduced_date, latest_action_date, latest_action_text,
                policy_area, committees_json, cosponsors_count
            FROM bills
            WHERE bill_id = :bill_id
            """,
            {"bill_id": bill_id}
        )
        row = cur.fetchone()

        if not row:
            return None

        (bill_id, congress, bill_type, bill_number, title,
         sponsor_name, sponsor_party, sponsor_state,
         introduced_date, latest_action_date, latest_action_text,
         policy_area, committees_json, cosponsors_count) = row

        # Build standard bill number format
        bill_type_upper = bill_type.upper().replace(".", "")
        bill_num_str = f"{bill_type_upper}{bill_number}"

        # Build Congress.gov URL
        url = f"https://www.congress.gov/bill/{congress}th-congress/{bill_type.lower()}/{bill_number}"

        metadata = {
            "sponsor_name": sponsor_name,
            "sponsor_party": sponsor_party,
            "sponsor_state": sponsor_state,
            "latest_action": latest_action_text,
            "policy_area": policy_area,
            "cosponsors_count": cosponsors_count,
        }

        if committees_json:
            try:
                metadata["committees"] = json.loads(committees_json)
            except json.JSONDecodeError:
                pass

        source_id = EvidenceSource.generate_source_id(SourceType.BILL, bill_id)

        return EvidenceSource(
            source_id=source_id,
            source_type=SourceType.BILL,
            title=title,
            url=url,
            date_published=introduced_date,
            date_accessed=utc_now_iso(),
            bill_number=bill_num_str,
            bill_congress=congress,
            issuing_agency="U.S. Congress",
            metadata=metadata,
        )
    finally:
        con.close()


def extract_bill_actions(bill_id: str) -> list[dict]:
    """
    Extract all actions for a bill.

    Args:
        bill_id: Bill identifier

    Returns:
        List of action dictionaries with date, text, and type
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT action_date, action_text, action_type
            FROM bill_actions
            WHERE bill_id = :bill_id
            ORDER BY action_date DESC
            """,
            {"bill_id": bill_id}
        )

        actions = []
        for row in cur.fetchall():
            actions.append({
                "date": row[0],
                "text": row[1],
                "type": row[2],
            })

        return actions
    finally:
        con.close()


def extract_bills_by_congress(congress: int) -> list[EvidenceSource]:
    """
    Extract all bills for a given Congress.

    Args:
        congress: Congress number (e.g., 118)

    Returns:
        List of EvidenceSource objects
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT
                bill_id, congress, bill_type, bill_number, title,
                introduced_date, latest_action_text
            FROM bills
            WHERE congress = :congress
            ORDER BY latest_action_date DESC
            """,
            {"congress": congress}
        )

        sources = []
        for row in cur.fetchall():
            bill_id, congress, bill_type, bill_number, title, introduced_date, latest_action = row
            bill_num_str = f"{bill_type.upper().replace('.', '')}{bill_number}"
            url = f"https://www.congress.gov/bill/{congress}th-congress/{bill_type.lower()}/{bill_number}"

            source_id = EvidenceSource.generate_source_id(SourceType.BILL, bill_id)
            sources.append(EvidenceSource(
                source_id=source_id,
                source_type=SourceType.BILL,
                title=title,
                url=url,
                date_published=introduced_date,
                date_accessed=utc_now_iso(),
                bill_number=bill_num_str,
                bill_congress=congress,
                issuing_agency="U.S. Congress",
            ))

        return sources
    finally:
        con.close()


# =============================================================================
# OVERSIGHT REPORT EXTRACTOR (GAO, OIG, CRS)
# =============================================================================

# Reuse patterns from deduplicator
GAO_PATTERN = re.compile(r"GAO-(\d{2})-(\d+)", re.IGNORECASE)
OIG_PATTERN = re.compile(r"(\d{2})-(\d{5})-(\d+)", re.IGNORECASE)
CRS_PATTERN = re.compile(r"(R\d{5}|RL\d{5}|RS\d{5})", re.IGNORECASE)


def extract_oversight_citation(event_id: str) -> Optional[EvidenceSource]:
    """
    Extract oversight report citation from om_events.

    Args:
        event_id: Oversight monitor event ID

    Returns:
        EvidenceSource with report details or None if not found
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT
                event_id, event_type, theme, primary_source_type, primary_url,
                pub_timestamp, pub_precision, pub_source,
                title, summary, canonical_refs, fetched_at
            FROM om_events
            WHERE event_id = :event_id
            """,
            {"event_id": event_id}
        )
        row = cur.fetchone()

        if not row:
            return None

        (event_id, event_type, theme, source_type, url,
         pub_timestamp, pub_precision, pub_source,
         title, summary, canonical_refs, fetched_at) = row

        # Determine source type
        st = SourceType.GAO_REPORT
        if source_type == "oig":
            st = SourceType.OIG_REPORT
        elif source_type == "crs":
            st = SourceType.CRS_REPORT
        elif source_type == "gao":
            st = SourceType.GAO_REPORT

        # Extract report number from canonical_refs
        report_number = None
        if canonical_refs:
            try:
                refs = json.loads(canonical_refs)
                report_number = refs.get("gao_report") or refs.get("oig_report") or refs.get("crs_report")
            except json.JSONDecodeError:
                pass

        # Try to extract from title if not in refs
        if not report_number:
            gao_match = GAO_PATTERN.search(title or "")
            if gao_match:
                report_number = f"GAO-{gao_match.group(1)}-{gao_match.group(2)}"
            else:
                oig_match = OIG_PATTERN.search(title or "")
                if oig_match:
                    report_number = "-".join(oig_match.groups())
                else:
                    crs_match = CRS_PATTERN.search(title or "")
                    if crs_match:
                        report_number = crs_match.group(1).upper()

        # Determine issuing agency
        agency_map = {
            "gao": "Government Accountability Office",
            "oig": "VA Office of Inspector General",
            "crs": "Congressional Research Service",
        }
        issuing_agency = agency_map.get(source_type, source_type)

        source_id = EvidenceSource.generate_source_id(st, event_id)

        return EvidenceSource(
            source_id=source_id,
            source_type=st,
            title=title,
            url=url,
            date_published=pub_timestamp,
            date_accessed=utc_now_iso(),
            report_number=report_number,
            issuing_agency=issuing_agency,
            document_type=event_type,
            metadata={
                "theme": theme,
                "summary": summary,
                "pub_precision": pub_precision,
                "pub_source": pub_source,
            },
        )
    finally:
        con.close()


def extract_oversight_citations_by_type(
    source_type: str,
    limit: int = 50
) -> list[EvidenceSource]:
    """
    Extract oversight citations by source type.

    Args:
        source_type: Source type (gao, oig, crs)
        limit: Maximum number to return

    Returns:
        List of EvidenceSource objects
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT
                event_id, event_type, theme, primary_source_type, primary_url,
                pub_timestamp, title, summary, canonical_refs
            FROM om_events
            WHERE primary_source_type = :source_type
            ORDER BY pub_timestamp DESC
            LIMIT :limit
            """,
            {"source_type": source_type, "limit": limit}
        )

        sources = []
        for row in cur.fetchall():
            event_id, event_type, theme, src_type, url, pub_ts, title, summary, canonical_refs = row

            st = SourceType.GAO_REPORT
            if src_type == "oig":
                st = SourceType.OIG_REPORT
            elif src_type == "crs":
                st = SourceType.CRS_REPORT

            report_number = None
            if canonical_refs:
                try:
                    refs = json.loads(canonical_refs)
                    report_number = refs.get("gao_report") or refs.get("oig_report") or refs.get("crs_report")
                except json.JSONDecodeError:
                    pass

            source_id = EvidenceSource.generate_source_id(st, event_id)
            sources.append(EvidenceSource(
                source_id=source_id,
                source_type=st,
                title=title,
                url=url,
                date_published=pub_ts,
                date_accessed=utc_now_iso(),
                report_number=report_number,
                issuing_agency=src_type.upper() if src_type else None,
            ))

        return sources
    finally:
        con.close()


def extract_oversight_by_theme(theme: str, limit: int = 50) -> list[EvidenceSource]:
    """
    Extract oversight citations by theme.

    Args:
        theme: Theme to filter by
        limit: Maximum number to return

    Returns:
        List of EvidenceSource objects
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT
                event_id, event_type, theme, primary_source_type, primary_url,
                pub_timestamp, title, canonical_refs
            FROM om_events
            WHERE theme LIKE :theme_pattern
            ORDER BY pub_timestamp DESC
            LIMIT :limit
            """,
            {"theme_pattern": f"%{theme}%", "limit": limit}
        )

        sources = []
        for row in cur.fetchall():
            event_id, event_type, th, src_type, url, pub_ts, title, canonical_refs = row

            st = SourceType.GAO_REPORT
            if src_type == "oig":
                st = SourceType.OIG_REPORT
            elif src_type == "crs":
                st = SourceType.CRS_REPORT

            source_id = EvidenceSource.generate_source_id(st, event_id)
            sources.append(EvidenceSource(
                source_id=source_id,
                source_type=st,
                title=title,
                url=url,
                date_published=pub_ts,
                date_accessed=utc_now_iso(),
                issuing_agency=src_type.upper() if src_type else None,
            ))

        return sources
    finally:
        con.close()


# =============================================================================
# HEARING EXTRACTOR
# =============================================================================

def extract_hearing_citation(event_id: str) -> Optional[EvidenceSource]:
    """
    Extract hearing citation from database.

    Args:
        event_id: Hearing event ID

    Returns:
        EvidenceSource with hearing details or None if not found
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT
                event_id, congress, chamber, committee_code, committee_name,
                hearing_date, hearing_time, title, meeting_type, status,
                location, url, witnesses_json
            FROM hearings
            WHERE event_id = :event_id
            """,
            {"event_id": event_id}
        )
        row = cur.fetchone()

        if not row:
            return None

        (event_id, congress, chamber, committee_code, committee_name,
         hearing_date, hearing_time, title, meeting_type, status,
         location, url, witnesses_json) = row

        metadata = {
            "chamber": chamber,
            "committee_code": committee_code,
            "committee_name": committee_name,
            "meeting_type": meeting_type,
            "status": status,
            "location": location,
        }

        if witnesses_json:
            try:
                metadata["witnesses"] = json.loads(witnesses_json)
            except json.JSONDecodeError:
                pass

        source_id = EvidenceSource.generate_source_id(SourceType.HEARING, event_id)

        return EvidenceSource(
            source_id=source_id,
            source_type=SourceType.HEARING,
            title=title or f"Hearing: {committee_name}",
            url=url or f"https://www.congress.gov/committee/{chamber.lower()}/{committee_code}",
            date_published=hearing_date,
            date_accessed=utc_now_iso(),
            bill_congress=congress,
            issuing_agency=committee_name,
            document_type=meeting_type or "hearing",
            metadata=metadata,
        )
    finally:
        con.close()


# =============================================================================
# AUTHORITY DOCUMENT EXTRACTOR
# =============================================================================

def extract_authority_doc_citation(doc_id: str) -> Optional[EvidenceSource]:
    """
    Extract authority document citation.

    Args:
        doc_id: Authority document ID

    Returns:
        EvidenceSource with document details or None if not found
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT
                doc_id, authority_source, authority_type, title,
                published_at, source_url, content_hash, version,
                metadata_json
            FROM authority_docs
            WHERE doc_id = :doc_id
            """,
            {"doc_id": doc_id}
        )
        row = cur.fetchone()

        if not row:
            return None

        (doc_id, authority_source, authority_type, title,
         published_at, source_url, content_hash, version,
         metadata_json) = row

        metadata = {}
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except json.JSONDecodeError:
                pass

        # Map authority source to agency name
        agency_map = {
            "whitehouse": "White House",
            "omb": "Office of Management and Budget",
            "va": "Department of Veterans Affairs",
            "omb_oira": "OMB/OIRA",
            "knowva": "KnowVA",
        }
        issuing_agency = agency_map.get(authority_source, authority_source)

        source_id = EvidenceSource.generate_source_id(SourceType.AUTHORITY_DOC, doc_id)

        return EvidenceSource(
            source_id=source_id,
            source_type=SourceType.AUTHORITY_DOC,
            title=title,
            url=source_url,
            date_published=published_at,
            date_accessed=utc_now_iso(),
            document_hash=content_hash,
            version=version,
            issuing_agency=issuing_agency,
            document_type=authority_type,
            metadata=metadata,
        )
    finally:
        con.close()


# =============================================================================
# TOPIC-BASED SEARCH
# =============================================================================

def search_citations_by_keyword(
    keyword: str,
    source_types: Optional[list[SourceType]] = None,
    limit: int = 20
) -> list[EvidenceSource]:
    """
    Search for citations containing a keyword across all source types.

    Args:
        keyword: Search term
        source_types: Optional filter by source types
        limit: Maximum results per source type

    Returns:
        List of EvidenceSource objects matching the keyword
    """
    results = []
    pattern = f"%{keyword}%"
    con = connect()

    try:
        # Search Federal Register
        if not source_types or SourceType.FEDERAL_REGISTER in source_types:
            cur = execute(
                con,
                """
                SELECT fs.doc_id, fs.published_date, fs.source_url, fsum.summary
                FROM fr_seen fs
                LEFT JOIN fr_summaries fsum ON fs.doc_id = fsum.doc_id
                WHERE fs.doc_id LIKE :pattern
                   OR fsum.summary LIKE :pattern
                   OR fsum.veteran_impact LIKE :pattern
                ORDER BY fs.published_date DESC
                LIMIT :limit
                """,
                {"pattern": pattern, "limit": limit}
            )
            for row in cur.fetchall():
                doc_id, pub_date, url, summary = row
                source_id = EvidenceSource.generate_source_id(SourceType.FEDERAL_REGISTER, doc_id)
                results.append(EvidenceSource(
                    source_id=source_id,
                    source_type=SourceType.FEDERAL_REGISTER,
                    title=f"FR Doc. {doc_id}",
                    url=url,
                    date_published=pub_date,
                    date_accessed=utc_now_iso(),
                    fr_doc_number=doc_id,
                    metadata={"summary": summary} if summary else {},
                ))

        # Search Bills
        if not source_types or SourceType.BILL in source_types:
            cur = execute(
                con,
                """
                SELECT bill_id, congress, bill_type, bill_number, title, introduced_date
                FROM bills
                WHERE title LIKE :pattern
                   OR bill_id LIKE :pattern
                   OR policy_area LIKE :pattern
                ORDER BY latest_action_date DESC
                LIMIT :limit
                """,
                {"pattern": pattern, "limit": limit}
            )
            for row in cur.fetchall():
                bill_id, congress, bill_type, bill_number, title, intro_date = row
                bill_num_str = f"{bill_type.upper().replace('.', '')}{bill_number}"
                url = f"https://www.congress.gov/bill/{congress}th-congress/{bill_type.lower()}/{bill_number}"
                source_id = EvidenceSource.generate_source_id(SourceType.BILL, bill_id)
                results.append(EvidenceSource(
                    source_id=source_id,
                    source_type=SourceType.BILL,
                    title=title,
                    url=url,
                    date_published=intro_date,
                    date_accessed=utc_now_iso(),
                    bill_number=bill_num_str,
                    bill_congress=congress,
                ))

        # Search Oversight events
        if not source_types or any(st in (source_types or []) for st in [SourceType.GAO_REPORT, SourceType.OIG_REPORT, SourceType.CRS_REPORT]):
            cur = execute(
                con,
                """
                SELECT event_id, primary_source_type, primary_url, pub_timestamp, title, summary
                FROM om_events
                WHERE title LIKE :pattern
                   OR summary LIKE :pattern
                   OR theme LIKE :pattern
                ORDER BY pub_timestamp DESC
                LIMIT :limit
                """,
                {"pattern": pattern, "limit": limit}
            )
            for row in cur.fetchall():
                event_id, src_type, url, pub_ts, title, summary = row
                st = SourceType.GAO_REPORT
                if src_type == "oig":
                    st = SourceType.OIG_REPORT
                elif src_type == "crs":
                    st = SourceType.CRS_REPORT
                source_id = EvidenceSource.generate_source_id(st, event_id)
                results.append(EvidenceSource(
                    source_id=source_id,
                    source_type=st,
                    title=title,
                    url=url,
                    date_published=pub_ts,
                    date_accessed=utc_now_iso(),
                    metadata={"summary": summary} if summary else {},
                ))

        return results
    finally:
        con.close()
