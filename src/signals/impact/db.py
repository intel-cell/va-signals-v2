"""Database operations for Impact Translation tables.

CHARLIE COMMAND - LOE 3: Impact Memos, Heat Maps, Objection Library.
"""

import json
from datetime import UTC, datetime

from ...db import connect, execute


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


# =============================================================================
# IMPACT MEMOS
# =============================================================================


def insert_impact_memo(memo: dict) -> str:
    """
    Insert a new impact memo. Returns memo_id.

    Expected keys match ImpactMemo.to_dict() output:
    - memo_id, issue_id, generated_date
    - policy_hook: {vehicle, vehicle_type, section_reference, current_status, source_url, effective_date}
    - what_it_does
    - why_it_matters: {operational_impact, affected_workflows, affected_veteran_count,
                       compliance_exposure, enforcement_mechanism, compliance_deadline,
                       cost_impact, cost_type, reputational_risk, narrative_vulnerability}
    - our_posture, recommended_action, decision_trigger
    - confidence_level, sources, translated_by, translation_method
    """
    con = connect()
    ph = memo["policy_hook"]
    wim = memo["why_it_matters"]

    execute(
        con,
        """INSERT INTO impact_memos(
             memo_id, issue_id, generated_date,
             policy_vehicle, policy_vehicle_type, policy_section_reference,
             policy_current_status, policy_source_url, policy_effective_date,
             what_it_does,
             operational_impact, affected_workflows, affected_veteran_count,
             compliance_exposure, enforcement_mechanism, compliance_deadline,
             cost_impact, cost_type, reputational_risk, narrative_vulnerability,
             our_posture, recommended_action, decision_trigger,
             confidence_level, sources_json, translated_by, translation_method
           ) VALUES (
             :memo_id, :issue_id, :generated_date,
             :policy_vehicle, :policy_vehicle_type, :policy_section_reference,
             :policy_current_status, :policy_source_url, :policy_effective_date,
             :what_it_does,
             :operational_impact, :affected_workflows, :affected_veteran_count,
             :compliance_exposure, :enforcement_mechanism, :compliance_deadline,
             :cost_impact, :cost_type, :reputational_risk, :narrative_vulnerability,
             :our_posture, :recommended_action, :decision_trigger,
             :confidence_level, :sources_json, :translated_by, :translation_method
           )""",
        {
            "memo_id": memo["memo_id"],
            "issue_id": memo["issue_id"],
            "generated_date": memo["generated_date"],
            "policy_vehicle": ph["vehicle"],
            "policy_vehicle_type": ph["vehicle_type"],
            "policy_section_reference": ph.get("section_reference"),
            "policy_current_status": ph["current_status"],
            "policy_source_url": ph["source_url"],
            "policy_effective_date": ph.get("effective_date"),
            "what_it_does": memo["what_it_does"],
            "operational_impact": wim["operational_impact"],
            "affected_workflows": json.dumps(wim["affected_workflows"]),
            "affected_veteran_count": wim.get("affected_veteran_count"),
            "compliance_exposure": wim["compliance_exposure"],
            "enforcement_mechanism": wim.get("enforcement_mechanism"),
            "compliance_deadline": wim.get("compliance_deadline"),
            "cost_impact": wim.get("cost_impact"),
            "cost_type": wim.get("cost_type"),
            "reputational_risk": wim["reputational_risk"],
            "narrative_vulnerability": wim.get("narrative_vulnerability"),
            "our_posture": memo["our_posture"],
            "recommended_action": memo["recommended_action"],
            "decision_trigger": memo["decision_trigger"],
            "confidence_level": memo["confidence_level"],
            "sources_json": json.dumps(memo.get("sources", [])),
            "translated_by": memo.get("translated_by", "charlie_command"),
            "translation_method": memo.get("translation_method", "rule_based"),
        },
    )
    con.commit()
    con.close()
    return memo["memo_id"]


def get_impact_memo(memo_id: str) -> dict | None:
    """Get a single impact memo by ID."""
    con = connect()
    cur = execute(
        con,
        """SELECT memo_id, issue_id, generated_date,
                  policy_vehicle, policy_vehicle_type, policy_section_reference,
                  policy_current_status, policy_source_url, policy_effective_date,
                  what_it_does,
                  operational_impact, affected_workflows, affected_veteran_count,
                  compliance_exposure, enforcement_mechanism, compliance_deadline,
                  cost_impact, cost_type, reputational_risk, narrative_vulnerability,
                  our_posture, recommended_action, decision_trigger,
                  confidence_level, sources_json, translated_by, translation_method,
                  created_at, updated_at
           FROM impact_memos WHERE memo_id = :memo_id""",
        {"memo_id": memo_id},
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return _memo_row_to_dict(row)


def _memo_row_to_dict(row) -> dict:
    """Convert a memo row to dictionary matching schema."""
    return {
        "memo_id": row[0],
        "issue_id": row[1],
        "generated_date": row[2],
        "policy_hook": {
            "vehicle": row[3],
            "vehicle_type": row[4],
            "section_reference": row[5],
            "current_status": row[6],
            "source_url": row[7],
            "effective_date": row[8],
        },
        "what_it_does": row[9],
        "why_it_matters": {
            "operational_impact": row[10],
            "affected_workflows": json.loads(row[11]) if row[11] else [],
            "affected_veteran_count": row[12],
            "compliance_exposure": row[13],
            "enforcement_mechanism": row[14],
            "compliance_deadline": row[15],
            "cost_impact": row[16],
            "cost_type": row[17],
            "reputational_risk": row[18],
            "narrative_vulnerability": row[19],
        },
        "our_posture": row[20],
        "recommended_action": row[21],
        "decision_trigger": row[22],
        "confidence_level": row[23],
        "sources": json.loads(row[24]) if row[24] else [],
        "translated_by": row[25],
        "translation_method": row[26],
        "created_at": row[27],
        "updated_at": row[28],
    }


def get_impact_memos(
    posture: str | None = None,
    compliance_exposure: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Get impact memos with optional filtering."""
    con = connect()
    query = """SELECT memo_id, issue_id, generated_date,
                      policy_vehicle, policy_vehicle_type, policy_section_reference,
                      policy_current_status, policy_source_url, policy_effective_date,
                      what_it_does,
                      operational_impact, affected_workflows, affected_veteran_count,
                      compliance_exposure, enforcement_mechanism, compliance_deadline,
                      cost_impact, cost_type, reputational_risk, narrative_vulnerability,
                      our_posture, recommended_action, decision_trigger,
                      confidence_level, sources_json, translated_by, translation_method,
                      created_at, updated_at
               FROM impact_memos WHERE 1=1"""
    params: dict = {}

    if posture:
        query += " AND our_posture = :posture"
        params["posture"] = posture

    if compliance_exposure:
        query += " AND compliance_exposure = :compliance_exposure"
        params["compliance_exposure"] = compliance_exposure

    query += " ORDER BY generated_date DESC LIMIT :limit"
    params["limit"] = limit

    cur = execute(con, query, params)
    rows = cur.fetchall()
    con.close()
    return [_memo_row_to_dict(r) for r in rows]


def get_memos_by_issue(issue_id: str) -> list[dict]:
    """Get all impact memos for a specific issue."""
    con = connect()
    cur = execute(
        con,
        """SELECT memo_id, issue_id, generated_date,
                  policy_vehicle, policy_vehicle_type, policy_section_reference,
                  policy_current_status, policy_source_url, policy_effective_date,
                  what_it_does,
                  operational_impact, affected_workflows, affected_veteran_count,
                  compliance_exposure, enforcement_mechanism, compliance_deadline,
                  cost_impact, cost_type, reputational_risk, narrative_vulnerability,
                  our_posture, recommended_action, decision_trigger,
                  confidence_level, sources_json, translated_by, translation_method,
                  created_at, updated_at
           FROM impact_memos WHERE issue_id = :issue_id
           ORDER BY generated_date DESC""",
        {"issue_id": issue_id},
    )
    rows = cur.fetchall()
    con.close()
    return [_memo_row_to_dict(r) for r in rows]


# =============================================================================
# HEAT MAPS
# =============================================================================


def insert_heat_map(heat_map: dict) -> str:
    """
    Insert a new heat map. Returns heat_map_id.

    Expected keys match HeatMap.to_dict() output:
    - heat_map_id, generated_date, issues[], summary
    """
    con = connect()
    execute(
        con,
        """INSERT INTO heat_maps(heat_map_id, generated_date, issues_json, summary_json)
           VALUES(:heat_map_id, :generated_date, :issues_json, :summary_json)""",
        {
            "heat_map_id": heat_map["heat_map_id"],
            "generated_date": heat_map["generated_date"],
            "issues_json": json.dumps(heat_map["issues"]),
            "summary_json": json.dumps(heat_map.get("summary", {})),
        },
    )

    # Also insert into denormalized heat_map_issues table for queries
    for issue in heat_map["issues"]:
        execute(
            con,
            """INSERT INTO heat_map_issues(
                 heat_map_id, issue_id, title, likelihood, impact,
                 urgency_days, score, quadrant, memo_id
               ) VALUES (
                 :heat_map_id, :issue_id, :title, :likelihood, :impact,
                 :urgency_days, :score, :quadrant, :memo_id
               )""",
            {
                "heat_map_id": heat_map["heat_map_id"],
                "issue_id": issue["issue_id"],
                "title": issue["title"],
                "likelihood": issue["likelihood"],
                "impact": issue["impact"],
                "urgency_days": issue["urgency_days"],
                "score": issue["score"],
                "quadrant": issue["quadrant"],
                "memo_id": issue.get("memo_id"),
            },
        )

    con.commit()
    con.close()
    return heat_map["heat_map_id"]


def get_latest_heat_map() -> dict | None:
    """Get the most recent heat map."""
    con = connect()
    cur = execute(
        con,
        """SELECT heat_map_id, generated_date, issues_json, summary_json, created_at
           FROM heat_maps ORDER BY generated_date DESC LIMIT 1""",
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "heat_map_id": row[0],
        "generated_date": row[1],
        "issues": json.loads(row[2]) if row[2] else [],
        "summary": json.loads(row[3]) if row[3] else {},
        "created_at": row[4],
    }


def get_heat_map(heat_map_id: str) -> dict | None:
    """Get a specific heat map by ID."""
    con = connect()
    cur = execute(
        con,
        """SELECT heat_map_id, generated_date, issues_json, summary_json, created_at
           FROM heat_maps WHERE heat_map_id = :heat_map_id""",
        {"heat_map_id": heat_map_id},
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "heat_map_id": row[0],
        "generated_date": row[1],
        "issues": json.loads(row[2]) if row[2] else [],
        "summary": json.loads(row[3]) if row[3] else {},
        "created_at": row[4],
    }


def get_high_priority_issues(limit: int = 10) -> list[dict]:
    """Get issues in high_priority quadrant from latest heat map, sorted by score."""
    con = connect()
    cur = execute(
        con,
        """SELECT hmi.issue_id, hmi.title, hmi.likelihood, hmi.impact,
                  hmi.urgency_days, hmi.score, hmi.quadrant, hmi.memo_id
           FROM heat_map_issues hmi
           JOIN (SELECT heat_map_id FROM heat_maps ORDER BY generated_date DESC LIMIT 1) latest
             ON hmi.heat_map_id = latest.heat_map_id
           WHERE hmi.quadrant = 'high_priority'
           ORDER BY hmi.score DESC
           LIMIT :limit""",
        {"limit": limit},
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "issue_id": r[0],
            "title": r[1],
            "likelihood": r[2],
            "impact": r[3],
            "urgency_days": r[4],
            "score": r[5],
            "quadrant": r[6],
            "memo_id": r[7],
        }
        for r in rows
    ]


# =============================================================================
# OBJECTION LIBRARY
# =============================================================================


def insert_objection(objection: dict) -> str:
    """
    Insert a new objection. Returns objection_id.

    Expected keys match Objection.to_dict() output:
    - objection_id, issue_area, source_type
    - objection_text, response_text
    - supporting_evidence, last_used_date, effectiveness_rating, tags
    """
    con = connect()
    execute(
        con,
        """INSERT INTO objections(
             objection_id, issue_area, source_type,
             objection_text, response_text,
             supporting_evidence_json, last_used_date, effectiveness_rating, tags_json
           ) VALUES (
             :objection_id, :issue_area, :source_type,
             :objection_text, :response_text,
             :supporting_evidence_json, :last_used_date, :effectiveness_rating, :tags_json
           )""",
        {
            "objection_id": objection["objection_id"],
            "issue_area": objection["issue_area"],
            "source_type": objection["source_type"],
            "objection_text": objection["objection_text"],
            "response_text": objection["response_text"],
            "supporting_evidence_json": json.dumps(objection.get("supporting_evidence", [])),
            "last_used_date": objection.get("last_used_date"),
            "effectiveness_rating": objection.get("effectiveness_rating"),
            "tags_json": json.dumps(objection.get("tags", [])),
        },
    )
    con.commit()
    con.close()
    return objection["objection_id"]


def get_objection(objection_id: str) -> dict | None:
    """Get a single objection by ID."""
    con = connect()
    cur = execute(
        con,
        """SELECT objection_id, issue_area, source_type,
                  objection_text, response_text,
                  supporting_evidence_json, last_used_date, effectiveness_rating, tags_json,
                  created_at, updated_at
           FROM objections WHERE objection_id = :objection_id""",
        {"objection_id": objection_id},
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return _objection_row_to_dict(row)


def _objection_row_to_dict(row) -> dict:
    """Convert an objection row to dictionary."""
    return {
        "objection_id": row[0],
        "issue_area": row[1],
        "source_type": row[2],
        "objection_text": row[3],
        "response_text": row[4],
        "supporting_evidence": json.loads(row[5]) if row[5] else [],
        "last_used_date": row[6],
        "effectiveness_rating": row[7],
        "tags": json.loads(row[8]) if row[8] else [],
        "created_at": row[9],
        "updated_at": row[10],
    }


def get_objections(
    issue_area: str | None = None,
    source_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Get objections with optional filtering."""
    con = connect()
    query = """SELECT objection_id, issue_area, source_type,
                      objection_text, response_text,
                      supporting_evidence_json, last_used_date, effectiveness_rating, tags_json,
                      created_at, updated_at
               FROM objections WHERE 1=1"""
    params: dict = {}

    if issue_area:
        query += " AND issue_area = :issue_area"
        params["issue_area"] = issue_area

    if source_type:
        query += " AND source_type = :source_type"
        params["source_type"] = source_type

    query += " ORDER BY effectiveness_rating DESC NULLS LAST, created_at DESC LIMIT :limit"
    params["limit"] = limit

    cur = execute(con, query, params)
    rows = cur.fetchall()
    con.close()
    return [_objection_row_to_dict(r) for r in rows]


def update_objection_usage(objection_id: str, effectiveness_rating: int | None = None) -> None:
    """Update objection's last_used_date and optionally effectiveness_rating."""
    con = connect()
    now = _utc_now_iso()

    if effectiveness_rating is not None:
        execute(
            con,
            """UPDATE objections
               SET last_used_date = :last_used_date,
                   effectiveness_rating = :effectiveness_rating,
                   updated_at = :updated_at
               WHERE objection_id = :objection_id""",
            {
                "objection_id": objection_id,
                "last_used_date": now,
                "effectiveness_rating": effectiveness_rating,
                "updated_at": now,
            },
        )
    else:
        execute(
            con,
            """UPDATE objections
               SET last_used_date = :last_used_date, updated_at = :updated_at
               WHERE objection_id = :objection_id""",
            {"objection_id": objection_id, "last_used_date": now, "updated_at": now},
        )

    con.commit()
    con.close()


def search_objections(query_text: str, limit: int = 10) -> list[dict]:
    """Search objections by text matching objection_text or response_text."""
    con = connect()
    search_pattern = f"%{query_text}%"
    cur = execute(
        con,
        """SELECT objection_id, issue_area, source_type,
                  objection_text, response_text,
                  supporting_evidence_json, last_used_date, effectiveness_rating, tags_json,
                  created_at, updated_at
           FROM objections
           WHERE objection_text LIKE :pattern OR response_text LIKE :pattern
           ORDER BY effectiveness_rating DESC NULLS LAST
           LIMIT :limit""",
        {"pattern": search_pattern, "limit": limit},
    )
    rows = cur.fetchall()
    con.close()
    return [_objection_row_to_dict(r) for r in rows]


def get_objection_stats() -> dict:
    """Get summary statistics for the objection library."""
    con = connect()

    # Total objections
    cur = execute(con, "SELECT COUNT(*) FROM objections")
    total = cur.fetchone()[0]

    # By issue area
    cur = execute(con, "SELECT issue_area, COUNT(*) FROM objections GROUP BY issue_area")
    by_issue_area = {r[0]: r[1] for r in cur.fetchall()}

    # By source type
    cur = execute(con, "SELECT source_type, COUNT(*) FROM objections GROUP BY source_type")
    by_source_type = {r[0]: r[1] for r in cur.fetchall()}

    # Average effectiveness
    cur = execute(
        con,
        "SELECT AVG(effectiveness_rating) FROM objections WHERE effectiveness_rating IS NOT NULL",
    )
    avg_effectiveness = cur.fetchone()[0]

    con.close()
    return {
        "total": total,
        "by_issue_area": by_issue_area,
        "by_source_type": by_source_type,
        "average_effectiveness": round(avg_effectiveness, 2) if avg_effectiveness else None,
    }
