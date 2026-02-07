"""
Battlefield Dashboard Pydantic Models

Schemas for vehicles, decision points, calendar events, and gate alerts
as specified in ORDER_DELTA_001.
"""

from enum import Enum

from pydantic import BaseModel, Field

# --- Enums ---


class VehicleType(str, Enum):
    """Types of legislative/regulatory vehicles we track."""

    BILL = "bill"
    RULE = "rule"
    APPROPRIATIONS = "appropriations"
    OVERSIGHT = "oversight"


class VehicleStage(str, Enum):
    """Current stage in the legislative/regulatory process."""

    # Legislative stages
    INTRODUCED = "introduced"
    COMMITTEE = "committee"
    MARKUP = "markup"
    FLOOR = "floor"
    CONFERENCE = "conference"
    ENACTED = "enacted"
    # Regulatory stages
    PROPOSED_RULE = "proposed_rule"
    FINAL_RULE = "final_rule"
    # Generic
    ACTIVE = "active"
    CLOSED = "closed"


class Posture(str, Enum):
    """Our organizational posture toward the vehicle."""

    SUPPORT = "support"
    OPPOSE = "oppose"
    MONITOR = "monitor"
    NEUTRAL_ENGAGED = "neutral_engaged"


class EventType(str, Enum):
    """Types of decision point events."""

    HEARING = "hearing"
    MARKUP = "markup"
    VOTE = "vote"
    COMMENT_DEADLINE = "comment_deadline"
    EFFECTIVE_DATE = "effective_date"
    FLOOR_ACTION = "floor_action"
    AMENDMENT = "amendment"


class Importance(str, Enum):
    """Importance level for calendar events."""

    CRITICAL = "critical"
    IMPORTANT = "important"
    WATCH = "watch"


class AlertType(str, Enum):
    """Types of gate alerts."""

    NEW_GATE = "new_gate"
    GATE_MOVED = "gate_moved"
    GATE_PASSED = "gate_passed"
    STATUS_CHANGED = "status_changed"


# --- Core Models ---


class VehicleStatus(BaseModel):
    """Current status of a vehicle."""

    current_stage: VehicleStage
    status_date: str
    status_text: str | None = None


class DecisionPoint(BaseModel):
    """Next decision point for a vehicle."""

    event_type: EventType
    date: str
    days_until: int
    time: str | None = None
    location: str | None = None
    description: str | None = None


class Vehicle(BaseModel):
    """
    A legislative/regulatory vehicle tracked on the battlefield.

    Per ORDER_DELTA_001 BATTLEFIELD_DASHBOARD schema.
    """

    vehicle_id: str = Field(..., description="Unique identifier for the vehicle")
    vehicle_type: VehicleType = Field(
        ..., description="Type: bill, rule, appropriations, oversight"
    )
    title: str = Field(..., description="Short title")
    identifier: str = Field(..., description="Official identifier (H.R. XXX, FR docket, etc.)")

    status: VehicleStatus = Field(..., description="Current status")
    next_decision_point: DecisionPoint | None = Field(None, description="Next gate/decision point")

    our_posture: Posture = Field(default=Posture.MONITOR, description="Organizational posture")
    attack_surface: str | None = Field(None, description="What could go wrong")
    owner_internal: str | None = Field(None, description="Internal owner tracking this")
    lobbyist_task: str | None = Field(None, description="Task for external team")

    heat_score: float | None = Field(None, description="Heat score from CHARLIE (0-100)")
    last_action: str | None = Field(None, description="Most recent action taken")
    evidence_pack_id: str | None = Field(None, description="Link to BRAVO evidence pack")

    source_url: str | None = Field(None, description="Primary source URL")
    created_at: str | None = None
    updated_at: str | None = None


class CalendarEvent(BaseModel):
    """
    A decision point event on the calendar.

    Per ORDER_DELTA_001 CALENDAR schema.
    """

    event_id: str = Field(..., description="Unique event identifier")
    vehicle_id: str = Field(..., description="Associated vehicle")
    date: str = Field(..., description="Event date (YYYY-MM-DD)")

    event_type: EventType = Field(..., description="Type of event")
    title: str = Field(..., description="Event title")
    time: str | None = Field(None, description="Time if known (HH:MM)")
    location: str | None = Field(None, description="Committee, chamber, etc.")

    importance: Importance = Field(default=Importance.WATCH, description="Importance level")
    prep_required: str | None = Field(None, description="What we need ready")

    days_until: int = Field(..., description="Days until event")
    source_type: str | None = Field(None, description="Source table/type")
    source_id: str | None = Field(None, description="ID in source table")


class GateAlert(BaseModel):
    """
    Alert when a decision gate moves or changes.

    Per ORDER_DELTA_001 GATE_ALERT schema.
    """

    alert_id: str = Field(..., description="Unique alert identifier")
    timestamp: str = Field(..., description="When alert was generated")
    vehicle_id: str = Field(..., description="Associated vehicle")

    alert_type: AlertType = Field(..., description="Type of alert")
    old_value: str | None = Field(None, description="Previous value")
    new_value: str = Field(..., description="New value")
    days_impact: int | None = Field(None, description="How much timeline shifted")

    recommended_action: str | None = Field(None, description="Suggested response")
    acknowledged: bool = Field(default=False, description="Has been reviewed")
    acknowledged_by: str | None = None
    acknowledged_at: str | None = None


# --- Aggregate Models ---


class Calendar(BaseModel):
    """
    Aggregated calendar view.

    Per ORDER_DELTA_001 CALENDAR schema.
    """

    date: str = Field(..., description="Calendar generation date")
    events: list[CalendarEvent] = Field(default_factory=list)

    # Summary counts
    total_events: int = 0
    critical_count: int = 0
    next_14_days_count: int = 0


class BattlefieldDashboard(BaseModel):
    """
    Complete battlefield dashboard state.

    Per ORDER_DELTA_001 BATTLEFIELD_DASHBOARD schema.
    """

    generated_date: str = Field(..., description="Dashboard generation timestamp")
    last_updated: str = Field(..., description="Last data update timestamp")

    vehicles: list[Vehicle] = Field(default_factory=list)

    # Summary stats
    total_vehicles: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_posture: dict[str, int] = Field(default_factory=dict)
    upcoming_gates_14d: int = 0


# --- API Response Models ---


class BattlefieldResponse(BaseModel):
    """API response for battlefield dashboard."""

    dashboard: BattlefieldDashboard
    calendar: Calendar
    recent_alerts: list[GateAlert] = Field(default_factory=list)


class CriticalGatesResponse(BaseModel):
    """Critical gates in next N days."""

    days: int
    events: list[CalendarEvent]
    count: int


class ActiveVehiclesResponse(BaseModel):
    """Active vehicles sorted by heat score."""

    vehicles: list[Vehicle]
    count: int


class RecentAlertsResponse(BaseModel):
    """Recent gate alerts."""

    hours: int
    alerts: list[GateAlert]
    count: int
