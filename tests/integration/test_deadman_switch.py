"""Tests for the dead-man's switch endpoint models and logic."""

import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from src.dashboard_api import PipelineStaleness, DeadManResponse


class TestDeadManModels:
    """Tests for dead-man's switch Pydantic models."""

    def test_pipeline_staleness_healthy(self):
        ps = PipelineStaleness(
            pipeline="oversight",
            last_activity_at="2026-02-06T10:00:00Z",
            hours_since_activity=2.5,
            status="healthy",
        )
        assert ps.status == "healthy"
        assert ps.hours_since_activity == 2.5

    def test_pipeline_staleness_critical_no_data(self):
        ps = PipelineStaleness(
            pipeline="state_intelligence",
            last_activity_at=None,
            hours_since_activity=None,
            status="critical",
        )
        assert ps.status == "critical"
        assert ps.last_activity_at is None

    def test_deadman_response_overall_status(self):
        pipelines = [
            PipelineStaleness(pipeline="a", last_activity_at=None, hours_since_activity=1.0, status="healthy"),
            PipelineStaleness(pipeline="b", last_activity_at=None, hours_since_activity=30.0, status="degraded"),
        ]
        resp = DeadManResponse(
            pipelines=pipelines,
            overall_status="degraded",
            checked_at="2026-02-06T12:00:00Z",
        )
        assert resp.overall_status == "degraded"
        assert len(resp.pipelines) == 2


class TestDeadManStatusClassification:
    """Tests for the status classification logic (healthy/degraded/critical thresholds)."""

    def _classify(self, hours):
        """Reproduce the classification logic from the endpoint."""
        if hours is None:
            return "critical"
        elif hours < 24:
            return "healthy"
        elif hours < 48:
            return "degraded"
        else:
            return "critical"

    def test_recent_activity_is_healthy(self):
        assert self._classify(0.5) == "healthy"
        assert self._classify(12.0) == "healthy"
        assert self._classify(23.99) == "healthy"

    def test_stale_activity_is_degraded(self):
        assert self._classify(24.0) == "degraded"
        assert self._classify(36.0) == "degraded"
        assert self._classify(47.99) == "degraded"

    def test_old_activity_is_critical(self):
        assert self._classify(48.0) == "critical"
        assert self._classify(72.0) == "critical"
        assert self._classify(168.0) == "critical"

    def test_none_hours_is_critical(self):
        assert self._classify(None) == "critical"


class TestDeadManOverallStatus:
    """Tests for overall_status derivation (worst of all pipelines)."""

    def test_all_healthy(self):
        statuses = ["healthy", "healthy", "healthy"]
        priority = {"critical": 2, "degraded": 1, "healthy": 0}
        overall = max(statuses, key=lambda s: priority[s])
        assert overall == "healthy"

    def test_one_degraded(self):
        statuses = ["healthy", "degraded", "healthy"]
        priority = {"critical": 2, "degraded": 1, "healthy": 0}
        overall = max(statuses, key=lambda s: priority[s])
        assert overall == "degraded"

    def test_one_critical_overrides_degraded(self):
        statuses = ["healthy", "degraded", "critical"]
        priority = {"critical": 2, "degraded": 1, "healthy": 0}
        overall = max(statuses, key=lambda s: priority[s])
        assert overall == "critical"
