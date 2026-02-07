"""Audit log writer for signal triggers."""

import json
from datetime import UTC, datetime

from src.db import connect, insert_returning_id
from src.signals.engine.evaluator import EvaluationResult


def write_audit_log(
    event_id: str,
    authority_id: str,
    indicator_id: str,
    trigger_id: str,
    severity: str,
    result: EvaluationResult,
    suppressed: bool = False,
    suppression_reason: str = None,
) -> int:
    """Write a trigger fire to the audit log. Returns row ID."""
    explanation = {
        "matched_terms": result.matched_terms,
        "matched_discriminators": result.matched_discriminators,
        "passed_evaluators": result.passed_evaluators,
        "failed_evaluators": result.failed_evaluators,
        "evidence_map": result.evidence_map,
    }

    con = connect()
    row_id = insert_returning_id(
        con,
        """
        INSERT INTO signal_audit_log
        (event_id, authority_id, indicator_id, trigger_id, severity, fired_at, suppressed, suppression_reason, explanation_json)
        VALUES (:event_id, :authority_id, :indicator_id, :trigger_id, :severity, :fired_at, :suppressed, :suppression_reason, :explanation_json)
        """,
        {
            "event_id": event_id,
            "authority_id": authority_id,
            "indicator_id": indicator_id,
            "trigger_id": trigger_id,
            "severity": severity,
            "fired_at": datetime.now(UTC).isoformat(),
            "suppressed": 1 if suppressed else 0,
            "suppression_reason": suppression_reason,
            "explanation_json": json.dumps(explanation),
        },
    )
    con.commit()
    con.close()
    return row_id
