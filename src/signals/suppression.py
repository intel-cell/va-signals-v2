"""Suppression manager for signal triggers."""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.db import connect


@dataclass
class SuppressionResult:
    """Result of suppression check."""
    suppressed: bool
    reason: Optional[str] = None  # "cooldown" | "dedupe" | None


class SuppressionManager:
    """Manages trigger suppression state."""

    def _make_dedupe_key(self, trigger_id: str, authority_id: str) -> str:
        """Create composite dedupe key."""
        return f"{trigger_id}:{authority_id}"

    def check_suppression(
        self,
        trigger_id: str,
        authority_id: str,
        version: int,
        cooldown_minutes: int,
        version_aware: bool,
    ) -> SuppressionResult:
        """Check if a trigger fire should be suppressed."""
        dedupe_key = self._make_dedupe_key(trigger_id, authority_id)
        now = datetime.now(timezone.utc)

        con = connect()
        cur = con.cursor()
        cur.execute(
            "SELECT version, cooldown_until FROM signal_suppression WHERE dedupe_key = ?",
            (dedupe_key,),
        )
        row = cur.fetchone()
        con.close()

        if row is None:
            return SuppressionResult(suppressed=False)

        stored_version, cooldown_until_str = row
        cooldown_until = datetime.fromisoformat(cooldown_until_str.replace("Z", "+00:00"))

        # Version bump bypasses cooldown if version_aware
        if version_aware and version > stored_version:
            return SuppressionResult(suppressed=False)

        # Check cooldown
        if now < cooldown_until:
            return SuppressionResult(suppressed=True, reason="cooldown")

        return SuppressionResult(suppressed=False)

    def record_fire(
        self,
        trigger_id: str,
        authority_id: str,
        version: int,
        cooldown_minutes: int,
    ) -> None:
        """Record a trigger fire for suppression tracking."""
        dedupe_key = self._make_dedupe_key(trigger_id, authority_id)
        now = datetime.now(timezone.utc)
        cooldown_until = now + timedelta(minutes=cooldown_minutes)

        con = connect()
        con.execute(
            """
            INSERT INTO signal_suppression (dedupe_key, trigger_id, authority_id, version, last_fired_at, cooldown_until)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(dedupe_key) DO UPDATE SET
                version = excluded.version,
                last_fired_at = excluded.last_fired_at,
                cooldown_until = excluded.cooldown_until
            """,
            (
                dedupe_key,
                trigger_id,
                authority_id,
                version,
                now.isoformat(),
                cooldown_until.isoformat(),
            ),
        )
        con.commit()
        con.close()
