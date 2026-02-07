"""Quality gate for oversight events - rejects events without publication timestamps."""

from dataclasses import dataclass

from src.oversight.agents.base import TimestampResult


@dataclass
class QualityGateResult:
    """Result of quality gate check."""

    passed: bool
    rejection_reason: str | None = None


def check_quality_gate(timestamps: TimestampResult, url: str) -> QualityGateResult:
    """
    Check if an event passes the quality gate.

    Requirement: pub_timestamp MUST exist (at least date precision).

    Args:
        timestamps: Extracted timestamp result
        url: Event URL (for logging)

    Returns:
        QualityGateResult indicating pass/fail
    """
    # Must have a publication timestamp
    if not timestamps.pub_timestamp:
        return QualityGateResult(
            passed=False,
            rejection_reason="temporal_incomplete",
        )

    # Timestamp must have meaningful precision
    if timestamps.pub_precision == "unknown" and not timestamps.pub_timestamp:
        return QualityGateResult(
            passed=False,
            rejection_reason="temporal_incomplete",
        )

    return QualityGateResult(passed=True)
