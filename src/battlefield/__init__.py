"""
Battlefield Dashboard Module

Provides situational awareness through:
- Vehicle tracking (bills, rules, appropriations, oversight)
- Decision point calendar aggregation
- Gate-moved detection and alerting

Integration points for:
- CHARLIE COMMAND: Heat scores
- BRAVO COMMAND: Evidence packs
- ALPHA COMMAND: Decision points for CEO Brief
"""

from .models import (
    Vehicle,
    VehicleStatus,
    DecisionPoint,
    CalendarEvent,
    GateAlert,
    BattlefieldDashboard,
    Calendar,
)

from .integrations import (
    receive_heat_score,
    batch_receive_heat_scores,
    get_vehicles_needing_heat_scores,
    receive_evidence_pack_link,
    batch_receive_evidence_packs,
    get_vehicles_needing_evidence_packs,
    get_decision_points_for_brief,
    get_active_vehicles_summary,
)

__all__ = [
    # Models
    "Vehicle",
    "VehicleStatus",
    "DecisionPoint",
    "CalendarEvent",
    "GateAlert",
    "BattlefieldDashboard",
    "Calendar",
    # CHARLIE integration
    "receive_heat_score",
    "batch_receive_heat_scores",
    "get_vehicles_needing_heat_scores",
    # BRAVO integration
    "receive_evidence_pack_link",
    "batch_receive_evidence_packs",
    "get_vehicles_needing_evidence_packs",
    # ALPHA integration
    "get_decision_points_for_brief",
    "get_active_vehicles_summary",
]
