"""Report generation endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from ..auth.models import UserRole
from ..auth.rbac import RoleChecker
from ..reports import generate_report

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Reports"])


@router.get("/api/reports/generate")
def generate_report_endpoint(
    type: str = Query("daily", description="Report type: daily or weekly"),
    format: str = Query("json", description="Output format: json"),
    _: None = Depends(RoleChecker(UserRole.ANALYST)),
):
    """Generate and return a report. Requires ANALYST role."""
    if type not in ("daily", "weekly"):
        raise HTTPException(status_code=400, detail="Invalid report type. Use 'daily' or 'weekly'")

    if format != "json":
        raise HTTPException(status_code=400, detail="Only 'json' format is supported")

    try:
        report = generate_report(type)
        return JSONResponse(content=report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")
