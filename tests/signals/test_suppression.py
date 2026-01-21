"""Tests for suppression manager."""

import pytest
from datetime import datetime, timezone, timedelta
from src.signals.suppression import SuppressionManager, SuppressionResult


@pytest.fixture
def manager(tmp_path, monkeypatch):
    """Create suppression manager with test DB."""
    import src.db as db_module
    test_db = tmp_path / "test_signals.db"
    monkeypatch.setattr(db_module, "DB_PATH", test_db)
    db_module.init_db()
    return SuppressionManager()


def test_first_fire_not_suppressed(manager):
    result = manager.check_suppression(
        trigger_id="formal_audit_signal",
        authority_id="GAO-26-123",
        version=1,
        cooldown_minutes=60,
        version_aware=True,
    )
    assert result.suppressed is False
    assert result.reason is None


def test_second_fire_within_cooldown_suppressed(manager):
    # First fire
    manager.check_suppression("t1", "auth-1", 1, 60, True)
    manager.record_fire("t1", "auth-1", 1, 60)

    # Second fire within cooldown
    result = manager.check_suppression("t1", "auth-1", 1, 60, True)
    assert result.suppressed is True
    assert result.reason == "cooldown"


def test_version_bump_bypasses_cooldown(manager):
    # First fire
    manager.check_suppression("t1", "auth-1", 1, 60, True)
    manager.record_fire("t1", "auth-1", 1, 60)

    # Second fire with version bump
    result = manager.check_suppression("t1", "auth-1", 2, 60, True)
    assert result.suppressed is False


def test_expired_cooldown_not_suppressed(manager):
    # First fire
    manager.check_suppression("t1", "auth-1", 1, 0, True)  # 0 minute cooldown
    manager.record_fire("t1", "auth-1", 1, 0)

    # Second fire after cooldown expired
    result = manager.check_suppression("t1", "auth-1", 1, 0, True)
    assert result.suppressed is False


def test_dedupe_key_composition(manager):
    key = manager._make_dedupe_key("trigger_1", "auth_123")
    assert "trigger_1" in key
    assert "auth_123" in key
