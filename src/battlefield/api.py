"""
Battlefield Dashboard API Endpoints

FastAPI router for battlefield dashboard, calendar, and alerts.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth.models import UserRole
from ..auth.rbac import RoleChecker
from .calendar import get_calendar_view, sync_all_sources
from .db_helpers import (
    acknowledge_alert,
    get_critical_gates,
    get_dashboard_stats,
    get_recent_alerts,
    get_vehicle,
    get_vehicles,
    get_vehicles_by_heat,
    init_battlefield_tables,
)
from .gate_detection import run_all_detections

router = APIRouter(prefix="/api/battlefield", tags=["battlefield"])


# --- Response Models ---


class DashboardStatsResponse(BaseModel):
    total_vehicles: int
    by_type: dict[str, int]
    by_posture: dict[str, int]
    upcoming_gates_14d: int
    alerts_48h: int
    unacknowledged_alerts: int


class SyncResponse(BaseModel):
    status: str
    results: dict


class AlertAckRequest(BaseModel):
    acknowledged_by: str


class VehicleUpdateRequest(BaseModel):
    our_posture: str | None = None
    owner_internal: str | None = None
    lobbyist_task: str | None = None
    attack_surface: str | None = None


# --- Endpoints ---


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_stats(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """Get battlefield dashboard summary statistics."""
    stats = get_dashboard_stats()
    return DashboardStatsResponse(**stats)


@router.get("/vehicles")
async def list_vehicles(
    vehicle_type: str | None = Query(
        None, description="Filter by type: bill, rule, appropriations, oversight"
    ),
    posture: str | None = Query(
        None, description="Filter by posture: support, oppose, monitor, neutral_engaged"
    ),
    stage: str | None = Query(None, description="Filter by stage"),
    limit: int = Query(50, ge=1, le=200),
    _: None = Depends(RoleChecker(UserRole.VIEWER)),
):
    """Get active vehicles, sorted by heat score."""
    vehicles = get_vehicles(
        vehicle_type=vehicle_type,
        posture=posture,
        stage=stage,
        limit=limit,
    )
    return {"vehicles": vehicles, "count": len(vehicles)}


@router.get("/vehicles/{vehicle_id}")
async def get_single_vehicle(vehicle_id: str, _: None = Depends(RoleChecker(UserRole.VIEWER))):
    """Get a single vehicle by ID."""
    vehicle = get_vehicle(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


@router.patch("/vehicles/{vehicle_id}")
async def update_vehicle(
    vehicle_id: str, updates: VehicleUpdateRequest, _: None = Depends(RoleChecker(UserRole.ANALYST))
):
    """Update vehicle posture, owner, or task."""
    vehicle = get_vehicle(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    # Apply updates
    update_dict = updates.model_dump(exclude_none=True)
    if update_dict:
        from datetime import datetime

        from ..db import execute

        set_clauses = ", ".join(f"{k} = :{k}" for k in update_dict.keys())
        update_dict["vehicle_id"] = vehicle_id
        update_dict["now"] = datetime.utcnow().isoformat()

        execute(
            f"UPDATE bf_vehicles SET {set_clauses}, updated_at = :now WHERE vehicle_id = :vehicle_id",
            update_dict,
        )

    return {"status": "updated", "vehicle_id": vehicle_id}


@router.get("/calendar")
async def get_calendar(
    days: int = Query(14, ge=1, le=90, description="Number of days to look ahead"),
    event_type: str | None = Query(None, description="Filter by event type"),
    importance: str | None = Query(None, description="Filter by importance"),
    _: None = Depends(RoleChecker(UserRole.VIEWER)),
):
    """Get calendar events for the next N days."""
    events = get_calendar_view(days=days)

    # Apply filters
    if event_type:
        events = [e for e in events if e.get("event_type") == event_type]
    if importance:
        events = [e for e in events if e.get("importance") == importance]

    return {
        "days": days,
        "events": events,
        "count": len(events),
    }


def _days_until(date_str: str) -> int:
    """Calculate days until a date from today."""
    from datetime import datetime

    try:
        target = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        today = datetime.utcnow().date()
        return (target - today).days
    except (ValueError, TypeError):
        return 999


@router.get("/critical-gates")
async def get_critical(
    days: int = Query(14, ge=1, le=30), _: None = Depends(RoleChecker(UserRole.VIEWER))
):
    """Get critical gates in the next N days."""
    events = get_critical_gates(days=days)
    # Add days_until to each event
    for event in events:
        event["days_until"] = _days_until(event.get("date", ""))
    return {"days": days, "events": events, "count": len(events)}


@router.get("/alerts")
async def get_alerts(
    hours: int = Query(48, ge=1, le=168, description="Hours to look back"),
    acknowledged: bool | None = Query(None, description="Filter by acknowledgment status"),
    _: None = Depends(RoleChecker(UserRole.VIEWER)),
):
    """Get recent gate alerts."""
    alerts = get_recent_alerts(hours=hours, acknowledged=acknowledged)
    return {"hours": hours, "alerts": alerts, "count": len(alerts)}


@router.post("/alerts/{alert_id}/acknowledge")
async def ack_alert(
    alert_id: str, request: AlertAckRequest, _: None = Depends(RoleChecker(UserRole.ANALYST))
):
    """Acknowledge a gate alert."""
    acknowledge_alert(alert_id, request.acknowledged_by)
    return {"status": "acknowledged", "alert_id": alert_id}


@router.post("/sync")
async def sync_calendar(_: None = Depends(RoleChecker(UserRole.LEADERSHIP))):
    """
    Sync all sources to battlefield calendar.

    This triggers a full sync of:
    - Hearings
    - Bills
    - Federal Register documents
    - Oversight events
    """
    try:
        results = sync_all_sources()
        return SyncResponse(status="success", results=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detect")
async def run_detection(_: None = Depends(RoleChecker(UserRole.LEADERSHIP))):
    """
    Run gate detection to find changes.

    This detects:
    - New hearings scheduled
    - Hearing date changes
    - Bill status changes
    - Oversight escalations
    - Passed gates
    """
    try:
        results = run_all_detections()
        return SyncResponse(status="success", results=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/init")
async def initialize_tables(_: None = Depends(RoleChecker(UserRole.COMMANDER))):
    """Initialize battlefield database tables."""
    try:
        init_battlefield_tables()
        return {"status": "initialized"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard")
async def get_full_dashboard(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """
    Get complete battlefield dashboard data.

    Returns:
    - Stats summary
    - Active vehicles (top 20 by heat)
    - Critical gates (next 14 days)
    - Recent alerts (last 48 hours)
    """
    stats = get_dashboard_stats()
    vehicles = get_vehicles_by_heat(limit=20)
    critical_gates = get_critical_gates(days=14)
    recent_alerts = get_recent_alerts(hours=48)

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "stats": stats,
        "vehicles": vehicles,
        "critical_gates": critical_gates,
        "recent_alerts": recent_alerts,
    }
