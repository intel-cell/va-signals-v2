"""
Evidence Pack Dashboard API Routes

HOTEL COMMAND - Phase 1 Integration
Exposes Evidence Pack system to Command Dashboard.

Endpoints:
- GET /api/evidence/packs - List evidence packs
- GET /api/evidence/packs/{pack_id} - Get pack details
- GET /api/evidence/packs/by-issue/{issue_id} - Get pack by issue
- GET /api/evidence/sources/{source_id} - Get source details
- GET /api/evidence/search - Search citations by topic
"""

from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel

from ..auth.rbac import RoleChecker
from ..auth.models import UserRole

from .api import (
    get_evidence_pack,
    get_evidence_pack_by_issue,
    list_evidence_packs,
    get_source_by_id,
    get_citations_for_topic,
)


router = APIRouter(prefix="/api/evidence", tags=["evidence"])


# --- Response Models ---

class EvidencePackSummary(BaseModel):
    pack_id: str
    issue_id: Optional[str]
    title: str
    generated_at: str
    status: str
    output_path: Optional[str]


class EvidencePackListResponse(BaseModel):
    packs: list[EvidencePackSummary]
    count: int


class EvidenceSourceResponse(BaseModel):
    source_id: str
    source_type: str
    title: str
    url: str
    date_accessed: Optional[str]
    date_published: Optional[str]
    fr_citation: Optional[str]
    bill_number: Optional[str]
    report_number: Optional[str]
    citation_string: Optional[str] = None


class CitationSearchResponse(BaseModel):
    citations: list[EvidenceSourceResponse]
    count: int
    query: str


# --- Endpoints ---

@router.get("/packs", response_model=EvidencePackListResponse)
async def list_packs(
    issue_id: Optional[str] = Query(None, description="Filter by issue ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200, description="Max packs to return"),
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """
    List available evidence packs.

    Returns summary information for filtering and display.
    """
    packs = list_evidence_packs(issue_id=issue_id, status=status, limit=limit)
    return EvidencePackListResponse(
        packs=[EvidencePackSummary(**p) for p in packs],
        count=len(packs),
    )


@router.get("/packs/{pack_id}")
async def get_pack(pack_id: str, _: None = Depends(RoleChecker(UserRole.ANALYST))):
    """
    Get full evidence pack details.

    Returns pack with all claims and sources.
    """
    pack = get_evidence_pack(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Evidence pack not found")

    # Convert to serializable dict
    return {
        "pack_id": pack.pack_id,
        "issue_id": pack.issue_id,
        "title": pack.title,
        "summary": pack.summary,
        "generated_at": pack.generated_at,
        "generated_by": pack.generated_by,
        "status": pack.status.value,
        "validation_errors": pack.validation_errors,
        "output_path": pack.output_path,
        "claims": [
            {
                "claim_id": c.claim_id,
                "claim_text": c.claim_text,
                "claim_type": c.claim_type.value,
                "confidence": c.confidence.value,
                "source_ids": c.source_ids,
                "last_verified": c.last_verified,
            }
            for c in pack.claims
        ],
        "sources": {
            sid: {
                "source_id": s.source_id,
                "source_type": s.source_type.value,
                "title": s.title,
                "url": s.url,
                "date_published": s.date_published,
                "date_accessed": s.date_accessed,
                "citation_string": s.to_citation_string(),
            }
            for sid, s in pack.sources.items()
        },
    }


@router.get("/packs/by-issue/{issue_id}")
async def get_pack_by_issue(issue_id: str, _: None = Depends(RoleChecker(UserRole.ANALYST))):
    """
    Get evidence pack for a specific issue.

    Returns the most recent pack for the issue.
    """
    pack = get_evidence_pack_by_issue(issue_id)
    if not pack:
        raise HTTPException(status_code=404, detail="No evidence pack for this issue")

    # Reuse the same serialization as get_pack
    return {
        "pack_id": pack.pack_id,
        "issue_id": pack.issue_id,
        "title": pack.title,
        "summary": pack.summary,
        "generated_at": pack.generated_at,
        "generated_by": pack.generated_by,
        "status": pack.status.value,
        "validation_errors": pack.validation_errors,
        "output_path": pack.output_path,
        "claims": [
            {
                "claim_id": c.claim_id,
                "claim_text": c.claim_text,
                "claim_type": c.claim_type.value,
                "confidence": c.confidence.value,
                "source_ids": c.source_ids,
                "last_verified": c.last_verified,
            }
            for c in pack.claims
        ],
        "sources": {
            sid: {
                "source_id": s.source_id,
                "source_type": s.source_type.value,
                "title": s.title,
                "url": s.url,
                "date_published": s.date_published,
                "date_accessed": s.date_accessed,
                "citation_string": s.to_citation_string(),
            }
            for sid, s in pack.sources.items()
        },
    }


@router.get("/sources/{source_id}")
async def get_source(source_id: str, _: None = Depends(RoleChecker(UserRole.ANALYST))):
    """
    Get source details by ID.

    Returns full source information for display or verification.
    """
    source = get_source_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    return source


@router.get("/search", response_model=CitationSearchResponse)
async def search_citations(
    q: str = Query(..., description="Search query (topic keywords)"),
    source_types: Optional[str] = Query(
        None,
        description="Comma-separated source types (federal_register,bill,hearing)"
    ),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """
    Search for citations by topic.

    Returns sources matching the search query, useful for
    finding evidence to support claims.
    """
    # Parse source types if provided
    st_list = None
    if source_types:
        st_list = [s.strip() for s in source_types.split(",") if s.strip()]

    citations = get_citations_for_topic(q, source_types=st_list, limit=limit)

    return CitationSearchResponse(
        citations=[
            EvidenceSourceResponse(
                source_id=c["source_id"],
                source_type=c["source_type"],
                title=c["title"],
                url=c["url"],
                date_accessed=c.get("date_accessed"),
                date_published=c.get("date_published"),
                fr_citation=c.get("fr_citation"),
                bill_number=c.get("bill_number"),
                report_number=c.get("report_number"),
                citation_string=c.get("citation_string"),
            )
            for c in citations
        ],
        count=len(citations),
        query=q,
    )
