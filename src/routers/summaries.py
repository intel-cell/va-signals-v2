"""Document summaries endpoints."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel

from ..db import connect, execute, table_exists
from ..auth.rbac import RoleChecker
from ..auth.models import UserRole

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Summaries"])


# --- Pydantic Models ---

class FRSummary(BaseModel):
    doc_id: str
    summary: str
    bullet_points: list[str]
    veteran_impact: str
    tags: list[str]
    summarized_at: str
    source_url: Optional[str] = None


class SummariesResponse(BaseModel):
    summaries: list[FRSummary]
    count: int


# --- Endpoints ---

@router.get("/api/summaries", response_model=SummariesResponse)
def get_summaries(
    limit: int = Query(50, ge=1, le=200, description="Number of summaries to return"),
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """Get recent document summaries with source URLs. Requires ANALYST role."""
    con = connect()
    # Check if fr_summaries table exists
    if not table_exists(con, "fr_summaries"):
        con.close()
        return SummariesResponse(summaries=[], count=0)

    # Join with fr_seen to get source_url
    cur = execute(
        con,
        """
        SELECT s.doc_id, s.summary, s.bullet_points, s.veteran_impact, s.tags,
               s.summarized_at, f.source_url
        FROM fr_summaries s
        LEFT JOIN fr_seen f ON s.doc_id = f.doc_id
        ORDER BY s.summarized_at DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    rows = cur.fetchall()
    con.close()

    summaries = []
    for row in rows:
        doc_id, summary, bullet_points_json, veteran_impact, tags_json, summarized_at, source_url = row
        try:
            bullet_points = json.loads(bullet_points_json) if bullet_points_json else []
        except (json.JSONDecodeError, TypeError):
            bullet_points = []
        try:
            tags = json.loads(tags_json) if tags_json else []
        except (json.JSONDecodeError, TypeError):
            tags = []

        summaries.append(
            FRSummary(
                doc_id=doc_id,
                summary=summary or "",
                bullet_points=bullet_points,
                veteran_impact=veteran_impact or "",
                tags=tags,
                summarized_at=summarized_at or "",
                source_url=source_url,
            )
        )

    return SummariesResponse(summaries=summaries, count=len(summaries))


@router.get("/api/summaries/{doc_id}", response_model=FRSummary)
def get_summary(doc_id: str, _: None = Depends(RoleChecker(UserRole.ANALYST))):
    """Get a specific document summary by doc_id. Requires ANALYST role."""
    con = connect()
    # Check if fr_summaries table exists
    if not table_exists(con, "fr_summaries"):
        con.close()
        raise HTTPException(status_code=404, detail="Summary not found")

    cur = execute(
        con,
        """
        SELECT s.doc_id, s.summary, s.bullet_points, s.veteran_impact, s.tags,
               s.summarized_at, f.source_url
        FROM fr_summaries s
        LEFT JOIN fr_seen f ON s.doc_id = f.doc_id
        WHERE s.doc_id = :doc_id
        """,
        {"doc_id": doc_id},
    )
    row = cur.fetchone()
    con.close()

    if not row:
        raise HTTPException(status_code=404, detail="Summary not found")

    doc_id, summary, bullet_points_json, veteran_impact, tags_json, summarized_at, source_url = row
    try:
        bullet_points = json.loads(bullet_points_json) if bullet_points_json else []
    except (json.JSONDecodeError, TypeError):
        bullet_points = []
    try:
        tags = json.loads(tags_json) if tags_json else []
    except (json.JSONDecodeError, TypeError):
        tags = []

    return FRSummary(
        doc_id=doc_id,
        summary=summary or "",
        bullet_points=bullet_points,
        veteran_impact=veteran_impact or "",
        tags=tags,
        summarized_at=summarized_at or "",
        source_url=source_url,
    )


@router.get("/api/summaries/check/{doc_id}")
def check_summary_exists(doc_id: str, _: None = Depends(RoleChecker(UserRole.ANALYST))):
    """Check if a summary exists for a given doc_id. Requires ANALYST role."""
    con = connect()
    # Check if fr_summaries table exists
    if not table_exists(con, "fr_summaries"):
        con.close()
        return {"exists": False}

    cur = execute(
        con,
        "SELECT 1 FROM fr_summaries WHERE doc_id = :doc_id",
        {"doc_id": doc_id},
    )
    exists = cur.fetchone() is not None
    con.close()

    return {"exists": exists}


@router.get("/api/summaries/doc-ids")
def get_summarized_doc_ids(_: None = Depends(RoleChecker(UserRole.ANALYST))):
    """Get list of all doc_ids that have summaries. Requires ANALYST role."""
    con = connect()
    # Check if fr_summaries table exists
    if not table_exists(con, "fr_summaries"):
        con.close()
        return {"doc_ids": []}

    cur = execute(con, "SELECT doc_id FROM fr_summaries")
    doc_ids = [row[0] for row in cur.fetchall()]
    con.close()

    return {"doc_ids": doc_ids}
