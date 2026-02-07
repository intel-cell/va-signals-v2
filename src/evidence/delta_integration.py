"""
BRAVO-DELTA Integration Module

Provides bridge functions for DELTA COMMAND (Battlefield Dashboard) to receive
evidence pack links from BRAVO COMMAND (Evidence Pack system).

Integration Points:
- Generate evidence packs for vehicles
- Link evidence packs to battlefield vehicles
- Query vehicles needing evidence packs
"""

import logging
from datetime import UTC, datetime

from src.db import connect, execute
from src.evidence.extractors import (
    extract_bill_citation,
    extract_fr_citation,
    extract_hearing_citation,
    extract_oversight_citation,
)
from src.evidence.generator import EvidencePackGenerator
from src.evidence.models import (
    ClaimType,
    Confidence,
    EvidenceSource,
    SourceType,
)

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


# ============================================================================
# DELTA INTEGRATION: Query Vehicles
# ============================================================================


def get_vehicles_needing_evidence_packs(limit: int = 100) -> list[dict]:
    """
    Get battlefield vehicles that don't have evidence packs linked.

    Queries DELTA's bf_vehicles table directly.

    Returns:
        List of vehicle dicts with vehicle_id, vehicle_type, identifier, etc.
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT vehicle_id, vehicle_type, title, identifier,
                   source_type, source_id, source_url
            FROM bf_vehicles
            WHERE evidence_pack_id IS NULL
            ORDER BY heat_score DESC NULLS LAST, status_date DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )

        vehicles = []
        for row in cur.fetchall():
            vehicles.append(
                {
                    "vehicle_id": row[0],
                    "vehicle_type": row[1],
                    "title": row[2],
                    "identifier": row[3],
                    "source_type": row[4],
                    "source_id": row[5],
                    "source_url": row[6],
                }
            )

        return vehicles
    except Exception as e:
        logger.warning(f"Could not query bf_vehicles: {e}")
        return []
    finally:
        con.close()


def get_vehicle_details(vehicle_id: str) -> dict | None:
    """
    Get full details for a single vehicle.

    Returns:
        Vehicle dict or None if not found
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT vehicle_id, vehicle_type, title, identifier,
                   current_stage, status_date, status_text,
                   our_posture, last_action, last_action_date,
                   source_type, source_id, source_url
            FROM bf_vehicles
            WHERE vehicle_id = :vehicle_id
            """,
            {"vehicle_id": vehicle_id},
        )
        row = cur.fetchone()

        if not row:
            return None

        return {
            "vehicle_id": row[0],
            "vehicle_type": row[1],
            "title": row[2],
            "identifier": row[3],
            "current_stage": row[4],
            "status_date": row[5],
            "status_text": row[6],
            "our_posture": row[7],
            "last_action": row[8],
            "last_action_date": row[9],
            "source_type": row[10],
            "source_id": row[11],
            "source_url": row[12],
        }
    except Exception as e:
        logger.warning(f"Could not get vehicle {vehicle_id}: {e}")
        return None
    finally:
        con.close()


# ============================================================================
# DELTA INTEGRATION: Link Evidence Packs
# ============================================================================


def link_evidence_pack_to_vehicle(
    vehicle_id: str,
    evidence_pack_id: str,
) -> bool:
    """
    Link an evidence pack to a battlefield vehicle.

    Updates DELTA's bf_vehicles table.

    Args:
        vehicle_id: Battlefield vehicle ID
        evidence_pack_id: BRAVO evidence pack ID

    Returns:
        True if successful, False otherwise
    """
    con = connect()
    try:
        execute(
            con,
            """
            UPDATE bf_vehicles
            SET evidence_pack_id = :evidence_pack_id,
                updated_at = datetime('now')
            WHERE vehicle_id = :vehicle_id
            """,
            {
                "vehicle_id": vehicle_id,
                "evidence_pack_id": evidence_pack_id,
            },
        )
        con.commit()
        logger.info(f"Linked evidence pack {evidence_pack_id} to vehicle {vehicle_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to link evidence pack: {e}")
        return False
    finally:
        con.close()


def batch_link_evidence_packs(links: list[dict]) -> dict:
    """
    Batch link evidence packs to vehicles.

    Args:
        links: List of {vehicle_id, evidence_pack_id} dicts

    Returns:
        {linked: int, failed: int, errors: list}
    """
    result = {"linked": 0, "failed": 0, "errors": []}

    for link in links:
        vehicle_id = link.get("vehicle_id")
        evidence_pack_id = link.get("evidence_pack_id")

        if not vehicle_id or not evidence_pack_id:
            result["errors"].append(f"Invalid link data: {link}")
            result["failed"] += 1
            continue

        if link_evidence_pack_to_vehicle(vehicle_id, evidence_pack_id):
            result["linked"] += 1
        else:
            result["failed"] += 1
            result["errors"].append(f"Failed to link {evidence_pack_id} to {vehicle_id}")

    logger.info(f"Batch link result: {result}")
    return result


# ============================================================================
# DELTA INTEGRATION: Generate Evidence Packs for Vehicles
# ============================================================================


def generate_evidence_pack_for_vehicle(
    vehicle_id: str,
    auto_link: bool = True,
) -> str | None:
    """
    Generate an evidence pack for a battlefield vehicle.

    Extracts the underlying source (bill, FR doc, hearing, etc.) and
    creates an evidence pack with citations.

    Args:
        vehicle_id: Battlefield vehicle ID
        auto_link: Whether to automatically link the pack to the vehicle

    Returns:
        Evidence pack ID if successful, None otherwise
    """
    # Get vehicle details
    vehicle = get_vehicle_details(vehicle_id)
    if not vehicle:
        logger.error(f"Vehicle not found: {vehicle_id}")
        return None

    # Determine source type and extract evidence
    source_type = vehicle.get("source_type")
    source_id = vehicle.get("source_id")
    vehicle_type = vehicle.get("vehicle_type")
    title = vehicle.get("title", "Unknown")
    identifier = vehicle.get("identifier", source_id)

    if not source_id:
        logger.error(f"Vehicle {vehicle_id} has no source_id")
        return None

    # Create evidence pack
    generator = EvidencePackGenerator(generated_by="bravo_delta_integration")
    pack = generator.create_pack(
        title=f"Evidence Pack: {identifier}",
        issue_id=vehicle_id,
        summary=f"Evidence supporting {vehicle_type}: {title}",
    )

    # Extract source based on type
    source = None
    if vehicle_type == "bill" or source_type == "bills":
        source = extract_bill_citation(source_id)
    elif vehicle_type == "rule" or source_type in ("fr_seen", "federal_register"):
        source = extract_fr_citation(source_id)
    elif source_type == "hearings":
        source = extract_hearing_citation(source_id)
    elif source_type == "om_events":
        source = extract_oversight_citation(source_id)

    if source:
        pack.add_source(source)

        # Create a claim about the vehicle
        status_text = vehicle.get("status_text") or vehicle.get("last_action") or "Status tracked"
        generator.add_claim(
            pack,
            claim_text=f"{identifier}: {status_text}",
            source_ids=[source.source_id],
            claim_type=ClaimType.OBSERVED,
            confidence=Confidence.HIGH,
        )
    else:
        # Create minimal source from vehicle data
        url = vehicle.get("source_url") or f"https://example.com/{source_id}"
        fallback_source = EvidenceSource(
            source_id=EvidenceSource.generate_source_id(SourceType.BILL, source_id),
            source_type=SourceType.BILL if vehicle_type == "bill" else SourceType.FEDERAL_REGISTER,
            title=title,
            url=url,
            date_accessed=utc_now_iso(),
            date_published=vehicle.get("status_date"),
        )
        pack.add_source(fallback_source)
        generator.add_claim(
            pack,
            claim_text=f"{identifier}: Tracked in battlefield dashboard",
            source_ids=[fallback_source.source_id],
            claim_type=ClaimType.OBSERVED,
            confidence=Confidence.MEDIUM,
        )

    # Validate and save
    try:
        generator.save_pack(pack, validate=True, strict=False)
        logger.info(f"Generated evidence pack {pack.pack_id} for vehicle {vehicle_id}")

        # Auto-link to vehicle
        if auto_link:
            link_evidence_pack_to_vehicle(vehicle_id, pack.pack_id)

        return pack.pack_id

    except Exception as e:
        logger.error(f"Failed to save evidence pack for {vehicle_id}: {e}")
        return None


def batch_generate_evidence_packs(
    vehicle_ids: list[str] | None = None,
    limit: int = 10,
    auto_link: bool = True,
) -> dict:
    """
    Generate evidence packs for multiple vehicles.

    Args:
        vehicle_ids: Specific vehicles to process (or None for auto-select)
        limit: Maximum vehicles to process if auto-selecting
        auto_link: Whether to auto-link packs to vehicles

    Returns:
        {generated: int, failed: int, pack_ids: list, errors: list}
    """
    result = {
        "generated": 0,
        "failed": 0,
        "pack_ids": [],
        "errors": [],
    }

    # Get vehicles to process
    if vehicle_ids:
        vehicles = [{"vehicle_id": vid} for vid in vehicle_ids]
    else:
        vehicles = get_vehicles_needing_evidence_packs(limit=limit)

    logger.info(f"Processing {len(vehicles)} vehicles for evidence pack generation")

    for vehicle in vehicles:
        vehicle_id = vehicle.get("vehicle_id")

        pack_id = generate_evidence_pack_for_vehicle(vehicle_id, auto_link=auto_link)

        if pack_id:
            result["generated"] += 1
            result["pack_ids"].append(pack_id)
        else:
            result["failed"] += 1
            result["errors"].append(f"Failed to generate pack for {vehicle_id}")

    logger.info(
        f"Batch generation result: {result['generated']} generated, {result['failed']} failed"
    )
    return result


# ============================================================================
# DELTA INTEGRATION: Query Evidence for Vehicle
# ============================================================================


def get_evidence_for_vehicle(vehicle_id: str) -> dict | None:
    """
    Get evidence pack details for a vehicle.

    Args:
        vehicle_id: Battlefield vehicle ID

    Returns:
        Evidence pack summary dict or None
    """
    from src.evidence.api import get_evidence_pack_by_issue

    pack = get_evidence_pack_by_issue(vehicle_id)
    if not pack:
        return None

    return {
        "pack_id": pack.pack_id,
        "title": pack.title,
        "status": pack.status.value,
        "generated_at": pack.generated_at,
        "claim_count": len(pack.claims),
        "source_count": len(pack.sources),
        "output_path": pack.output_path,
    }


def get_vehicles_with_evidence_summary(limit: int = 50) -> list[dict]:
    """
    Get vehicles with their evidence pack status.

    Returns list of vehicles with evidence pack summary.
    """
    con = connect()
    try:
        cur = execute(
            con,
            """
            SELECT v.vehicle_id, v.vehicle_type, v.identifier, v.title,
                   v.evidence_pack_id, v.heat_score,
                   ep.status as pack_status, ep.generated_at as pack_generated
            FROM bf_vehicles v
            LEFT JOIN evidence_packs ep ON v.evidence_pack_id = ep.pack_id
            ORDER BY v.heat_score DESC NULLS LAST
            LIMIT :limit
            """,
            {"limit": limit},
        )

        results = []
        for row in cur.fetchall():
            results.append(
                {
                    "vehicle_id": row[0],
                    "vehicle_type": row[1],
                    "identifier": row[2],
                    "title": row[3],
                    "evidence_pack_id": row[4],
                    "heat_score": row[5],
                    "pack_status": row[6],
                    "pack_generated": row[7],
                    "has_evidence": row[4] is not None,
                }
            )

        return results
    except Exception as e:
        logger.warning(f"Could not query vehicles with evidence: {e}")
        return []
    finally:
        con.close()


# Convenience exports
__all__ = [
    "get_vehicles_needing_evidence_packs",
    "get_vehicle_details",
    "link_evidence_pack_to_vehicle",
    "batch_link_evidence_packs",
    "generate_evidence_pack_for_vehicle",
    "batch_generate_evidence_packs",
    "get_evidence_for_vehicle",
    "get_vehicles_with_evidence_summary",
]
