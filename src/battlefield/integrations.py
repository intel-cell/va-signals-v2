"""
Battlefield Integrations

Integration points for:
- CHARLIE COMMAND: Heat scores (likelihood x impact x urgency)
- BRAVO COMMAND: Evidence pack links

These functions provide the interface for other commands to push data
to the battlefield dashboard.
"""

import logging
from typing import Optional
from datetime import datetime

from .db_helpers import (
    get_vehicle,
    get_vehicles,
    update_vehicle_heat_score,
    update_vehicle_evidence_pack,
    _execute_write,
)

logger = logging.getLogger(__name__)


# ============================================================================
# CHARLIE INTEGRATION: Heat Scores
# ============================================================================

def receive_heat_score(
    vehicle_id: str,
    heat_score: float,
    likelihood: Optional[float] = None,
    impact: Optional[float] = None,
    urgency: Optional[float] = None,
) -> bool:
    """
    Receive heat score from CHARLIE COMMAND.

    Heat score formula: likelihood * impact * urgency (normalized to 0-100)

    Args:
        vehicle_id: Battlefield vehicle ID
        heat_score: Composite score (0-100)
        likelihood: Component score (optional, for audit)
        impact: Component score (optional, for audit)
        urgency: Component score (optional, for audit)

    Returns:
        True if vehicle found and updated, False otherwise.
    """
    vehicle = get_vehicle(vehicle_id)
    if not vehicle:
        logger.warning(f"CHARLIE integration: Vehicle not found: {vehicle_id}")
        return False

    update_vehicle_heat_score(vehicle_id, heat_score)
    logger.info(f"CHARLIE integration: Updated heat score for {vehicle_id}: {heat_score}")

    return True


def batch_receive_heat_scores(scores: list[dict]) -> dict:
    """
    Receive batch of heat scores from CHARLIE COMMAND.

    Args:
        scores: List of {vehicle_id, heat_score, ...}

    Returns:
        {updated: int, not_found: int, errors: list}
    """
    result = {"updated": 0, "not_found": 0, "errors": []}

    for score_data in scores:
        vehicle_id = score_data.get("vehicle_id")
        heat_score = score_data.get("heat_score")

        if not vehicle_id or heat_score is None:
            result["errors"].append(f"Invalid score data: {score_data}")
            continue

        if receive_heat_score(vehicle_id, heat_score):
            result["updated"] += 1
        else:
            result["not_found"] += 1

    logger.info(f"CHARLIE batch integration: {result}")
    return result


def get_vehicles_needing_heat_scores(limit: int = 100) -> list[dict]:
    """
    Get vehicles that don't have heat scores assigned.

    Used by CHARLIE to identify what needs scoring.

    Returns:
        List of vehicles with null heat_score.
    """
    vehicles = get_vehicles(limit=limit)
    return [v for v in vehicles if v.get("heat_score") is None]


# ============================================================================
# BRAVO INTEGRATION: Evidence Packs
# ============================================================================

def receive_evidence_pack_link(
    vehicle_id: str,
    evidence_pack_id: str,
    pack_type: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> bool:
    """
    Receive evidence pack link from BRAVO COMMAND.

    Args:
        vehicle_id: Battlefield vehicle ID
        evidence_pack_id: ID of evidence pack in BRAVO system
        pack_type: Type of pack (optional, e.g., "citation", "impact")
        generated_at: When pack was generated (optional)

    Returns:
        True if vehicle found and updated, False otherwise.
    """
    vehicle = get_vehicle(vehicle_id)
    if not vehicle:
        logger.warning(f"BRAVO integration: Vehicle not found: {vehicle_id}")
        return False

    update_vehicle_evidence_pack(vehicle_id, evidence_pack_id)
    logger.info(f"BRAVO integration: Linked evidence pack {evidence_pack_id} to {vehicle_id}")

    return True


def batch_receive_evidence_packs(packs: list[dict]) -> dict:
    """
    Receive batch of evidence pack links from BRAVO COMMAND.

    Args:
        packs: List of {vehicle_id, evidence_pack_id, ...}

    Returns:
        {linked: int, not_found: int, errors: list}
    """
    result = {"linked": 0, "not_found": 0, "errors": []}

    for pack_data in packs:
        vehicle_id = pack_data.get("vehicle_id")
        evidence_pack_id = pack_data.get("evidence_pack_id")

        if not vehicle_id or not evidence_pack_id:
            result["errors"].append(f"Invalid pack data: {pack_data}")
            continue

        if receive_evidence_pack_link(vehicle_id, evidence_pack_id):
            result["linked"] += 1
        else:
            result["not_found"] += 1

    logger.info(f"BRAVO batch integration: {result}")
    return result


def get_vehicles_needing_evidence_packs(limit: int = 100) -> list[dict]:
    """
    Get vehicles that don't have evidence packs linked.

    Used by BRAVO to identify what needs citation packs.

    Returns:
        List of vehicles with null evidence_pack_id.
    """
    vehicles = get_vehicles(limit=limit)
    return [v for v in vehicles if v.get("evidence_pack_id") is None]


# ============================================================================
# ALPHA INTEGRATION: Decision Points for CEO Brief
# ============================================================================

def get_decision_points_for_brief(days: int = 14) -> list[dict]:
    """
    Get upcoming decision points for ALPHA COMMAND CEO Brief.

    Returns:
        List of critical/important calendar events with vehicle context.
    """
    from .db_helpers import get_critical_gates
    return get_critical_gates(days=days)


def get_active_vehicles_summary() -> dict:
    """
    Get summary of active vehicles for CEO Brief.

    Returns:
        {total: int, by_type: dict, by_posture: dict, top_heat: list}
    """
    from .db_helpers import get_dashboard_stats, get_vehicles_by_heat

    stats = get_dashboard_stats()
    top_vehicles = get_vehicles_by_heat(limit=10)

    return {
        "total": stats["total_vehicles"],
        "by_type": stats["by_type"],
        "by_posture": stats["by_posture"],
        "upcoming_gates_14d": stats["upcoming_gates_14d"],
        "top_vehicles": [
            {
                "identifier": v["identifier"],
                "title": v["title"][:100],
                "vehicle_type": v["vehicle_type"],
                "heat_score": v["heat_score"],
                "status_date": v["status_date"],
            }
            for v in top_vehicles
        ],
    }
