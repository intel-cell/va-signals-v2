"""
Battlefield Dashboard Database Helpers

Database operations for vehicles, calendar events, and gate alerts.
"""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from ..db import connect
from ..db import execute as db_execute

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _execute(sql: str, params: dict | None = None) -> list[dict]:
    """Execute a query and return results as list of dicts."""
    conn = connect()
    conn.row_factory = lambda cursor, row: (
        {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
        if cursor.description
        else {}
    )
    cursor = db_execute(conn, sql, params)
    try:
        results = cursor.fetchall()
    except Exception:
        results = []
    return results


def _execute_write(sql: str, params: dict | None = None) -> None:
    """Execute a write query (INSERT, UPDATE, DELETE)."""
    conn = connect()
    db_execute(conn, sql, params)
    conn.commit()


def init_battlefield_tables() -> None:
    """Initialize battlefield tables from schema.sql."""
    from ..db import init_db

    init_db()


def generate_id(prefix: str = "bf") -> str:
    """Generate a unique ID with prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --- Vehicle Operations ---


def upsert_vehicle(
    vehicle_id: str,
    vehicle_type: str,
    title: str,
    identifier: str,
    current_stage: str,
    status_date: str,
    status_text: str | None = None,
    our_posture: str = "monitor",
    attack_surface: str | None = None,
    owner_internal: str | None = None,
    lobbyist_task: str | None = None,
    heat_score: float | None = None,
    evidence_pack_id: str | None = None,
    last_action: str | None = None,
    last_action_date: str | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    source_url: str | None = None,
) -> str:
    """Insert or update a vehicle."""
    now = datetime.utcnow().isoformat()

    _execute_write(
        """
        INSERT INTO bf_vehicles (
            vehicle_id, vehicle_type, title, identifier,
            current_stage, status_date, status_text,
            our_posture, attack_surface, owner_internal, lobbyist_task,
            heat_score, evidence_pack_id,
            last_action, last_action_date,
            source_type, source_id, source_url,
            created_at, updated_at
        ) VALUES (
            :vehicle_id, :vehicle_type, :title, :identifier,
            :current_stage, :status_date, :status_text,
            :our_posture, :attack_surface, :owner_internal, :lobbyist_task,
            :heat_score, :evidence_pack_id,
            :last_action, :last_action_date,
            :source_type, :source_id, :source_url,
            :now, :now
        )
        ON CONFLICT(vehicle_id) DO UPDATE SET
            title = :title,
            current_stage = :current_stage,
            status_date = :status_date,
            status_text = :status_text,
            our_posture = :our_posture,
            attack_surface = :attack_surface,
            owner_internal = :owner_internal,
            lobbyist_task = :lobbyist_task,
            heat_score = :heat_score,
            evidence_pack_id = :evidence_pack_id,
            last_action = :last_action,
            last_action_date = :last_action_date,
            updated_at = :now
        """,
        {
            "vehicle_id": vehicle_id,
            "vehicle_type": vehicle_type,
            "title": title,
            "identifier": identifier,
            "current_stage": current_stage,
            "status_date": status_date,
            "status_text": status_text,
            "our_posture": our_posture,
            "attack_surface": attack_surface,
            "owner_internal": owner_internal,
            "lobbyist_task": lobbyist_task,
            "heat_score": heat_score,
            "evidence_pack_id": evidence_pack_id,
            "last_action": last_action,
            "last_action_date": last_action_date,
            "source_type": source_type,
            "source_id": source_id,
            "source_url": source_url,
            "now": now,
        },
    )
    return vehicle_id


def get_vehicle(vehicle_id: str) -> dict | None:
    """Get a single vehicle by ID."""
    rows = _execute(
        "SELECT * FROM bf_vehicles WHERE vehicle_id = :vehicle_id",
        {"vehicle_id": vehicle_id},
    )
    return rows[0] if rows else None


def get_vehicles(
    vehicle_type: str | None = None,
    posture: str | None = None,
    stage: str | None = None,
    limit: int = 100,
    order_by: str = "heat_score DESC NULLS LAST, updated_at DESC",
) -> list[dict]:
    """Get vehicles with optional filters."""
    conditions = []
    params = {"limit": limit}

    if vehicle_type:
        conditions.append("vehicle_type = :vehicle_type")
        params["vehicle_type"] = vehicle_type

    if posture:
        conditions.append("our_posture = :posture")
        params["posture"] = posture

    if stage:
        conditions.append("current_stage = :stage")
        params["stage"] = stage

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # SQLite doesn't support NULLS LAST, use COALESCE workaround
    if "NULLS LAST" in order_by:
        order_by = order_by.replace("heat_score DESC NULLS LAST", "COALESCE(heat_score, -1) DESC")

    rows = _execute(
        f"SELECT * FROM bf_vehicles {where} ORDER BY {order_by} LIMIT :limit",
        params,
    )
    return rows


def get_vehicles_by_heat(limit: int = 50) -> list[dict]:
    """Get vehicles sorted by heat score descending."""
    return get_vehicles(limit=limit, order_by="COALESCE(heat_score, -1) DESC, updated_at DESC")


def update_vehicle_heat_score(vehicle_id: str, heat_score: float) -> None:
    """Update heat score for a vehicle (from CHARLIE integration)."""
    _execute_write(
        """
        UPDATE bf_vehicles
        SET heat_score = :heat_score, updated_at = :now
        WHERE vehicle_id = :vehicle_id
        """,
        {
            "vehicle_id": vehicle_id,
            "heat_score": heat_score,
            "now": datetime.utcnow().isoformat(),
        },
    )


def update_vehicle_evidence_pack(vehicle_id: str, evidence_pack_id: str) -> None:
    """Link evidence pack to vehicle (from BRAVO integration)."""
    _execute_write(
        """
        UPDATE bf_vehicles
        SET evidence_pack_id = :evidence_pack_id, updated_at = :now
        WHERE vehicle_id = :vehicle_id
        """,
        {
            "vehicle_id": vehicle_id,
            "evidence_pack_id": evidence_pack_id,
            "now": datetime.utcnow().isoformat(),
        },
    )


# --- Calendar Event Operations ---


def upsert_calendar_event(
    event_id: str,
    vehicle_id: str,
    date: str,
    event_type: str,
    title: str,
    time: str | None = None,
    location: str | None = None,
    importance: str = "watch",
    prep_required: str | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
) -> str:
    """Insert or update a calendar event."""
    now = datetime.utcnow().isoformat()

    _execute_write(
        """
        INSERT INTO bf_calendar_events (
            event_id, vehicle_id, date, event_type, title,
            time, location, importance, prep_required,
            source_type, source_id,
            created_at, updated_at
        ) VALUES (
            :event_id, :vehicle_id, :date, :event_type, :title,
            :time, :location, :importance, :prep_required,
            :source_type, :source_id,
            :now, :now
        )
        ON CONFLICT(event_id) DO UPDATE SET
            date = :date,
            event_type = :event_type,
            title = :title,
            time = :time,
            location = :location,
            importance = :importance,
            prep_required = :prep_required,
            updated_at = :now
        """,
        {
            "event_id": event_id,
            "vehicle_id": vehicle_id,
            "date": date,
            "event_type": event_type,
            "title": title,
            "time": time,
            "location": location,
            "importance": importance,
            "prep_required": prep_required,
            "source_type": source_type,
            "source_id": source_id,
            "now": now,
        },
    )
    return event_id


def get_calendar_events(
    start_date: str | None = None,
    end_date: str | None = None,
    event_type: str | None = None,
    importance: str | None = None,
    vehicle_id: str | None = None,
    include_passed: bool = False,
    limit: int = 100,
) -> list[dict]:
    """Get calendar events with filters."""
    conditions = []
    params = {"limit": limit}

    if start_date:
        conditions.append("date >= :start_date")
        params["start_date"] = start_date

    if end_date:
        conditions.append("date <= :end_date")
        params["end_date"] = end_date

    if event_type:
        conditions.append("event_type = :event_type")
        params["event_type"] = event_type

    if importance:
        conditions.append("importance = :importance")
        params["importance"] = importance

    if vehicle_id:
        conditions.append("vehicle_id = :vehicle_id")
        params["vehicle_id"] = vehicle_id

    if not include_passed:
        conditions.append("passed = 0")
        conditions.append("cancelled = 0")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = _execute(
        f"""
        SELECT * FROM bf_calendar_events
        {where}
        ORDER BY date ASC, importance DESC
        LIMIT :limit
        """,
        params,
    )
    return rows


def get_critical_gates(days: int = 14) -> list[dict]:
    """Get critical and important events in the next N days."""
    today = datetime.utcnow().date().isoformat()
    end_date = (datetime.utcnow().date() + timedelta(days=days)).isoformat()

    rows = _execute(
        """
        SELECT e.*, v.title as vehicle_title, v.identifier, v.our_posture
        FROM bf_calendar_events e
        JOIN bf_vehicles v ON e.vehicle_id = v.vehicle_id
        WHERE e.date >= :today
          AND e.date <= :end_date
          AND e.passed = 0
          AND e.cancelled = 0
          AND e.importance IN ('critical', 'important')
        ORDER BY e.date ASC, e.importance DESC
        """,
        {"today": today, "end_date": end_date},
    )
    return rows


def mark_event_passed(event_id: str) -> None:
    """Mark a calendar event as passed."""
    _execute_write(
        "UPDATE bf_calendar_events SET passed = 1, updated_at = :now WHERE event_id = :event_id",
        {"event_id": event_id, "now": datetime.utcnow().isoformat()},
    )


# --- Gate Alert Operations ---


def create_gate_alert(
    vehicle_id: str,
    alert_type: str,
    new_value: str,
    old_value: str | None = None,
    days_impact: int | None = None,
    recommended_action: str | None = None,
    source_event_id: str | None = None,
    source_type: str | None = None,
) -> str:
    """Create a new gate alert."""
    alert_id = generate_id("alert")
    now = datetime.utcnow().isoformat()

    _execute_write(
        """
        INSERT INTO bf_gate_alerts (
            alert_id, timestamp, vehicle_id,
            alert_type, old_value, new_value, days_impact,
            recommended_action, source_event_id, source_type,
            created_at
        ) VALUES (
            :alert_id, :timestamp, :vehicle_id,
            :alert_type, :old_value, :new_value, :days_impact,
            :recommended_action, :source_event_id, :source_type,
            :now
        )
        """,
        {
            "alert_id": alert_id,
            "timestamp": now,
            "vehicle_id": vehicle_id,
            "alert_type": alert_type,
            "old_value": old_value,
            "new_value": new_value,
            "days_impact": days_impact,
            "recommended_action": recommended_action,
            "source_event_id": source_event_id,
            "source_type": source_type,
            "now": now,
        },
    )
    return alert_id


def get_recent_alerts(hours: int = 48, acknowledged: bool | None = None) -> list[dict]:
    """Get recent gate alerts."""
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    conditions = ["timestamp >= :cutoff"]
    params = {"cutoff": cutoff}

    if acknowledged is not None:
        conditions.append("acknowledged = :acknowledged")
        params["acknowledged"] = 1 if acknowledged else 0

    where = f"WHERE {' AND '.join(conditions)}"

    rows = _execute(
        f"""
        SELECT a.*, v.title as vehicle_title, v.identifier
        FROM bf_gate_alerts a
        JOIN bf_vehicles v ON a.vehicle_id = v.vehicle_id
        {where}
        ORDER BY a.timestamp DESC
        """,
        params,
    )
    return rows


def acknowledge_alert(alert_id: str, acknowledged_by: str) -> None:
    """Acknowledge a gate alert."""
    _execute_write(
        """
        UPDATE bf_gate_alerts
        SET acknowledged = 1, acknowledged_by = :acknowledged_by, acknowledged_at = :now
        WHERE alert_id = :alert_id
        """,
        {
            "alert_id": alert_id,
            "acknowledged_by": acknowledged_by,
            "now": datetime.utcnow().isoformat(),
        },
    )


# --- Dashboard Stats ---


def get_dashboard_stats() -> dict:
    """Get summary statistics for the battlefield dashboard."""
    # Total vehicles by type
    type_rows = _execute(
        "SELECT vehicle_type, COUNT(*) as count FROM bf_vehicles GROUP BY vehicle_type"
    )
    by_type = {r["vehicle_type"]: r["count"] for r in type_rows}

    # Vehicles by posture
    posture_rows = _execute(
        "SELECT our_posture, COUNT(*) as count FROM bf_vehicles GROUP BY our_posture"
    )
    by_posture = {r["our_posture"]: r["count"] for r in posture_rows}

    # Upcoming gates in 14 days
    today = datetime.utcnow().date().isoformat()
    end_14d = (datetime.utcnow().date() + timedelta(days=14)).isoformat()
    gates_rows = _execute(
        """
        SELECT COUNT(*) as count FROM bf_calendar_events
        WHERE date >= :today AND date <= :end_14d AND passed = 0 AND cancelled = 0
        """,
        {"today": today, "end_14d": end_14d},
    )
    upcoming_gates_14d = gates_rows[0]["count"] if gates_rows else 0

    # Alerts in last 48 hours
    cutoff_48h = (datetime.utcnow() - timedelta(hours=48)).isoformat()
    alerts_rows = _execute(
        "SELECT COUNT(*) as count FROM bf_gate_alerts WHERE timestamp >= :cutoff",
        {"cutoff": cutoff_48h},
    )
    alerts_48h = alerts_rows[0]["count"] if alerts_rows else 0

    # Unacknowledged alerts
    unack_rows = _execute("SELECT COUNT(*) as count FROM bf_gate_alerts WHERE acknowledged = 0")
    unacknowledged_alerts = unack_rows[0]["count"] if unack_rows else 0

    return {
        "total_vehicles": sum(by_type.values()),
        "by_type": by_type,
        "by_posture": by_posture,
        "upcoming_gates_14d": upcoming_gates_14d,
        "alerts_48h": alerts_48h,
        "unacknowledged_alerts": unacknowledged_alerts,
    }


# --- Snapshot Operations ---


def save_snapshot() -> int:
    """Save a daily snapshot for trend analysis."""
    stats = get_dashboard_stats()
    now = datetime.utcnow()

    _execute_write(
        """
        INSERT INTO bf_snapshots (
            snapshot_date, total_vehicles, total_critical_gates,
            total_alerts_24h, by_type_json, by_posture_json, created_at
        ) VALUES (
            :snapshot_date, :total_vehicles, :total_critical_gates,
            :total_alerts_24h, :by_type_json, :by_posture_json, :now
        )
        """,
        {
            "snapshot_date": now.date().isoformat(),
            "total_vehicles": stats["total_vehicles"],
            "total_critical_gates": stats["upcoming_gates_14d"],
            "total_alerts_24h": stats["alerts_48h"],  # Approximation
            "by_type_json": json.dumps(stats["by_type"]),
            "by_posture_json": json.dumps(stats["by_posture"]),
            "now": now.isoformat(),
        },
    )

    # Return 0 since we can't easily get lastrowid with this pattern
    return 0
