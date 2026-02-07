"""Integration API for Evidence Pack system.

This API is used by other commands (ALPHA, CHARLIE, DELTA) to:
- Get evidence packs for issues
- Validate claims against sources
- Get citations for topics

Functions:
- get_evidence_pack(issue_id) -> EvidencePack
- validate_claim(claim_text, source_ids) -> bool
- get_citations_for_topic(topic) -> List[EvidenceSource]
"""

import json

from src.db import connect, execute
from src.evidence.extractors import (
    search_citations_by_keyword,
)
from src.evidence.models import (
    ClaimType,
    Confidence,
    EvidenceClaim,
    EvidencePack,
    EvidenceSource,
    PackStatus,
    SourceType,
)
from src.evidence.validator import (
    validate_claim as _validate_claim,
)


def get_evidence_pack(pack_id: str) -> EvidencePack | None:
    """
    Retrieve an evidence pack by ID.

    Args:
        pack_id: Evidence pack ID

    Returns:
        EvidencePack if found, None otherwise
    """
    con = connect()
    try:
        # Get pack metadata
        cur = execute(
            con,
            """
            SELECT pack_id, issue_id, title, summary, generated_at, generated_by,
                   status, validation_errors, output_path
            FROM evidence_packs
            WHERE pack_id = :pack_id
            """,
            {"pack_id": pack_id},
        )
        row = cur.fetchone()

        if not row:
            return None

        (
            pack_id,
            issue_id,
            title,
            summary,
            generated_at,
            generated_by,
            status,
            validation_errors,
            output_path,
        ) = row

        pack = EvidencePack(
            pack_id=pack_id,
            title=title,
            issue_id=issue_id,
            summary=summary,
            generated_at=generated_at,
            generated_by=generated_by,
            status=PackStatus(status) if status else PackStatus.DRAFT,
            validation_errors=json.loads(validation_errors) if validation_errors else [],
            output_path=output_path,
        )

        # Get claims
        cur = execute(
            con,
            """
            SELECT claim_id, claim_text, claim_type, confidence, last_verified
            FROM evidence_claims
            WHERE pack_id = :pack_id
            """,
            {"pack_id": pack_id},
        )

        claim_rows = cur.fetchall()
        for claim_row in claim_rows:
            claim_id, claim_text, claim_type, confidence, last_verified = claim_row

            # Get source IDs for this claim
            cur = execute(
                con,
                """
                SELECT source_id
                FROM evidence_claim_sources
                WHERE claim_id = :claim_id
                """,
                {"claim_id": claim_id},
            )
            source_ids = [r[0] for r in cur.fetchall()]

            claim = EvidenceClaim(
                claim_id=claim_id,
                claim_text=claim_text,
                claim_type=ClaimType(claim_type) if claim_type else ClaimType.OBSERVED,
                confidence=Confidence(confidence) if confidence else Confidence.HIGH,
                source_ids=source_ids,
                last_verified=last_verified,
            )
            pack.claims.append(claim)

        # Get sources referenced by claims
        all_source_ids = set()
        for claim in pack.claims:
            all_source_ids.update(claim.source_ids)

        for source_id in all_source_ids:
            cur = execute(
                con,
                """
                SELECT source_id, source_type, title, date_published, date_effective,
                       date_accessed, url, document_hash, version,
                       fr_citation, fr_doc_number, bill_number, bill_congress,
                       report_number, issuing_agency, document_type, metadata_json
                FROM evidence_sources
                WHERE source_id = :source_id
                """,
                {"source_id": source_id},
            )
            src_row = cur.fetchone()

            if src_row:
                (
                    source_id,
                    source_type,
                    title,
                    date_published,
                    date_effective,
                    date_accessed,
                    url,
                    document_hash,
                    version,
                    fr_citation,
                    fr_doc_number,
                    bill_number,
                    bill_congress,
                    report_number,
                    issuing_agency,
                    document_type,
                    metadata_json,
                ) = src_row

                source = EvidenceSource(
                    source_id=source_id,
                    source_type=SourceType(source_type),
                    title=title,
                    url=url,
                    date_published=date_published,
                    date_effective=date_effective,
                    date_accessed=date_accessed,
                    document_hash=document_hash,
                    version=version,
                    fr_citation=fr_citation,
                    fr_doc_number=fr_doc_number,
                    bill_number=bill_number,
                    bill_congress=bill_congress,
                    report_number=report_number,
                    issuing_agency=issuing_agency,
                    document_type=document_type,
                    metadata=json.loads(metadata_json) if metadata_json else {},
                )
                pack.sources[source_id] = source

        return pack
    finally:
        con.close()


def get_evidence_pack_by_issue(issue_id: str) -> EvidencePack | None:
    """
    Retrieve the most recent evidence pack for an issue.

    Args:
        issue_id: Issue identifier

    Returns:
        Most recent EvidencePack for issue, or None
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT pack_id
            FROM evidence_packs
            WHERE issue_id = :issue_id
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            {"issue_id": issue_id},
        )
        row = cur.fetchone()

        if not row:
            return None

        return get_evidence_pack(row[0])
    finally:
        con.close()


def validate_claim(claim_text: str, source_ids: list[str]) -> tuple[bool, list[str]]:
    """
    Validate that a claim has proper supporting sources.

    This is the API endpoint for other commands to validate claims
    before including them in outputs.

    Args:
        claim_text: The claim statement
        source_ids: List of source IDs cited

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    if not source_ids:
        return (False, ["Claim must have at least one supporting source"])

    # Load sources from database
    con = connect()
    available_sources = {}
    try:
        for source_id in source_ids:
            cur = execute(
                con,
                """
                SELECT source_id, source_type, title, url, date_accessed, date_published
                FROM evidence_sources
                WHERE source_id = :source_id
                """,
                {"source_id": source_id},
            )
            row = cur.fetchone()

            if row:
                source_id, source_type, title, url, date_accessed, date_published = row
                available_sources[source_id] = EvidenceSource(
                    source_id=source_id,
                    source_type=SourceType(source_type),
                    title=title,
                    url=url,
                    date_accessed=date_accessed,
                    date_published=date_published,
                )
    finally:
        con.close()

    # Build claim object and validate
    claim = EvidenceClaim(
        claim_text=claim_text,
        source_ids=source_ids,
    )

    result = _validate_claim(claim, available_sources)
    return (result.passed, result.errors)


def get_citations_for_topic(
    topic: str, source_types: list[str] | None = None, limit: int = 20
) -> list[dict]:
    """
    Get citations relevant to a topic.

    This is the API endpoint for other commands to find sources
    for their outputs.

    Args:
        topic: Topic keyword(s) to search
        source_types: Optional filter by source type names
        limit: Maximum citations to return

    Returns:
        List of citation dicts with source details
    """
    # Convert source type names to enums
    st_filter = None
    if source_types:
        st_filter = []
        for st in source_types:
            try:
                st_filter.append(SourceType(st))
            except ValueError:
                pass

    sources = search_citations_by_keyword(topic, source_types=st_filter, limit=limit)

    return [
        {
            "source_id": s.source_id,
            "source_type": s.source_type.value,
            "title": s.title,
            "url": s.url,
            "date_published": s.date_published,
            "date_accessed": s.date_accessed,
            "fr_citation": s.fr_citation,
            "bill_number": s.bill_number,
            "report_number": s.report_number,
            "citation_string": s.to_citation_string(),
        }
        for s in sources
    ]


def get_source_by_id(source_id: str) -> dict | None:
    """
    Get a source by its ID.

    Args:
        source_id: Source identifier

    Returns:
        Source dict or None
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT source_id, source_type, title, url, date_accessed, date_published,
                   fr_citation, fr_doc_number, bill_number, bill_congress,
                   report_number, issuing_agency, document_type
            FROM evidence_sources
            WHERE source_id = :source_id
            """,
            {"source_id": source_id},
        )
        row = cur.fetchone()

        if not row:
            return None

        (
            source_id,
            source_type,
            title,
            url,
            date_accessed,
            date_published,
            fr_citation,
            fr_doc_number,
            bill_number,
            bill_congress,
            report_number,
            issuing_agency,
            document_type,
        ) = row

        return {
            "source_id": source_id,
            "source_type": source_type,
            "title": title,
            "url": url,
            "date_accessed": date_accessed,
            "date_published": date_published,
            "fr_citation": fr_citation,
            "fr_doc_number": fr_doc_number,
            "bill_number": bill_number,
            "bill_congress": bill_congress,
            "report_number": report_number,
            "issuing_agency": issuing_agency,
            "document_type": document_type,
        }
    finally:
        con.close()


def register_source(
    source_type: str,
    title: str,
    url: str,
    date_accessed: str,
    date_published: str | None = None,
    **kwargs,
) -> str:
    """
    Register a new source in the evidence database.

    Use this when other commands need to add sources that aren't
    already in the system.

    Args:
        source_type: Type of source (federal_register, bill, etc.)
        title: Source title
        url: Primary source URL
        date_accessed: When source was accessed
        date_published: When source was published
        **kwargs: Additional source-specific fields

    Returns:
        source_id of the registered source
    """
    st = SourceType(source_type)
    identifier = (
        kwargs.get("fr_doc_number")
        or kwargs.get("bill_number")
        or kwargs.get("report_number")
        or url
    )
    source_id = EvidenceSource.generate_source_id(st, identifier)

    con = connect()
    try:
        execute(
            con,
            """
            INSERT INTO evidence_sources (
                source_id, source_type, title, date_published, date_accessed, url,
                fr_citation, fr_doc_number, bill_number, bill_congress,
                report_number, issuing_agency, document_type
            ) VALUES (
                :source_id, :source_type, :title, :date_published, :date_accessed, :url,
                :fr_citation, :fr_doc_number, :bill_number, :bill_congress,
                :report_number, :issuing_agency, :document_type
            ) ON CONFLICT(source_id) DO UPDATE SET
                date_accessed = :date_accessed,
                updated_at = datetime('now')
            """,
            {
                "source_id": source_id,
                "source_type": source_type,
                "title": title,
                "date_published": date_published,
                "date_accessed": date_accessed,
                "url": url,
                "fr_citation": kwargs.get("fr_citation"),
                "fr_doc_number": kwargs.get("fr_doc_number"),
                "bill_number": kwargs.get("bill_number"),
                "bill_congress": kwargs.get("bill_congress"),
                "report_number": kwargs.get("report_number"),
                "issuing_agency": kwargs.get("issuing_agency"),
                "document_type": kwargs.get("document_type"),
            },
        )
        con.commit()
    finally:
        con.close()

    return source_id


def list_evidence_packs(
    issue_id: str | None = None, status: str | None = None, limit: int = 50
) -> list[dict]:
    """
    List available evidence packs.

    Args:
        issue_id: Optional filter by issue
        status: Optional filter by status
        limit: Maximum packs to return

    Returns:
        List of pack summary dicts
    """
    con = connect()
    try:
        where_clauses = []
        params = {"limit": limit}

        if issue_id:
            where_clauses.append("issue_id = :issue_id")
            params["issue_id"] = issue_id

        if status:
            where_clauses.append("status = :status")
            params["status"] = status

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        cur = execute(
            con,
            f"""
            SELECT pack_id, issue_id, title, generated_at, status, output_path
            FROM evidence_packs
            WHERE {where_sql}
            ORDER BY generated_at DESC
            LIMIT :limit
            """,
            params,
        )

        return [
            {
                "pack_id": row[0],
                "issue_id": row[1],
                "title": row[2],
                "generated_at": row[3],
                "status": row[4],
                "output_path": row[5],
            }
            for row in cur.fetchall()
        ]
    finally:
        con.close()
