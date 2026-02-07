"""Tests for src.resilience.canary module."""

import sqlite3
from datetime import UTC, datetime
from unittest.mock import patch

from src.resilience.canary import (
    no_duplicate_ids,
    run_canaries,
    timestamps_monotonic,
    weekday_has_documents,
)


class TestWeekdayHasDocuments:
    """Tests for weekday_has_documents canary."""

    def test_flags_failure_on_weekday_with_zero_docs(self):
        """Should fail on a weekday when 0 documents fetched."""
        # Mock a Monday
        mock_now = datetime(2026, 2, 2, 12, 0, 0, tzinfo=UTC)  # Monday
        with patch("src.resilience.canary.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = weekday_has_documents(
                "govinfo_fr_bulk",
                run_record={"records_fetched": 0},
            )
        assert result.passed is False
        assert "0 documents" in result.message

    def test_passes_on_weekday_with_docs(self):
        """Should pass on a weekday when documents are fetched."""
        mock_now = datetime(2026, 2, 2, 12, 0, 0, tzinfo=UTC)  # Monday
        with patch("src.resilience.canary.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = weekday_has_documents(
                "govinfo_fr_bulk",
                run_record={"records_fetched": 5},
            )
        assert result.passed is True

    def test_passes_on_weekend(self):
        """Should pass on weekends regardless of document count."""
        mock_now = datetime(2026, 2, 7, 12, 0, 0, tzinfo=UTC)  # Saturday
        with patch("src.resilience.canary.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = weekday_has_documents(
                "govinfo_fr_bulk",
                run_record={"records_fetched": 0},
            )
        assert result.passed is True
        assert "Weekend" in result.message


class TestNoDuplicateIds:
    """Tests for no_duplicate_ids canary using in-memory SQLite."""

    def _make_db_with_dupes(self):
        """Create an in-memory SQLite DB with duplicate doc_ids."""
        con = sqlite3.connect(":memory:")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE fr_seen (doc_id TEXT, first_seen_at TEXT)")
        con.execute("INSERT INTO fr_seen VALUES ('DOC-001', '2026-01-01')")
        con.execute("INSERT INTO fr_seen VALUES ('DOC-001', '2026-01-02')")  # duplicate
        con.execute("INSERT INTO fr_seen VALUES ('DOC-002', '2026-01-03')")
        con.commit()
        return con

    def _make_db_no_dupes(self):
        """Create an in-memory SQLite DB with unique doc_ids."""
        con = sqlite3.connect(":memory:")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE fr_seen (doc_id TEXT, first_seen_at TEXT)")
        con.execute("INSERT INTO fr_seen VALUES ('DOC-001', '2026-01-01')")
        con.execute("INSERT INTO fr_seen VALUES ('DOC-002', '2026-01-02')")
        con.execute("INSERT INTO fr_seen VALUES ('DOC-003', '2026-01-03')")
        con.commit()
        return con

    def test_catches_duplicates(self):
        """Should detect duplicate values."""
        con = self._make_db_with_dupes()
        with patch("src.db.connect", return_value=con):
            result = no_duplicate_ids("fr_seen", "doc_id")
        assert result.passed is False
        assert "DOC-001" in result.message
        assert result.severity == "critical"

    def test_passes_no_duplicates(self):
        """Should pass when no duplicates exist."""
        con = self._make_db_no_dupes()
        with patch("src.db.connect", return_value=con):
            result = no_duplicate_ids("fr_seen", "doc_id")
        assert result.passed is True


class TestTimestampsMonotonic:
    """Tests for timestamps_monotonic canary."""

    def _make_db_monotonic(self):
        """Create DB with monotonically increasing timestamps."""
        con = sqlite3.connect(":memory:")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE source_runs (ended_at TEXT)")
        for ts in [
            "2026-01-01T01:00:00",
            "2026-01-01T02:00:00",
            "2026-01-01T03:00:00",
            "2026-01-01T04:00:00",
        ]:
            con.execute("INSERT INTO source_runs VALUES (?)", (ts,))
        con.commit()
        return con

    def _make_db_non_monotonic(self):
        """Create DB with non-monotonic timestamps."""
        con = sqlite3.connect(":memory:")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE source_runs (ended_at TEXT)")
        for ts in [
            "2026-01-01T01:00:00",
            "2026-01-01T03:00:00",
            "2026-01-01T02:00:00",  # out of order
            "2026-01-01T04:00:00",
        ]:
            con.execute("INSERT INTO source_runs VALUES (?)", (ts,))
        con.commit()
        return con

    def test_passes_monotonic(self):
        """Should pass when timestamps are non-decreasing."""
        con = self._make_db_monotonic()
        with patch("src.db.connect", return_value=con):
            result = timestamps_monotonic("source_runs", "ended_at")
        assert result.passed is True

    def test_catches_non_monotonic(self):
        """Should catch non-monotonic timestamps."""
        con = self._make_db_non_monotonic()
        with patch("src.db.connect", return_value=con):
            result = timestamps_monotonic("source_runs", "ended_at")
        assert result.passed is False
        assert "Non-monotonic" in result.message


class TestRunCanaries:
    """Tests for run_canaries orchestrator."""

    def test_returns_empty_for_unknown_source(self):
        """Should return empty list for unregistered source_id."""
        results = run_canaries("nonexistent_source", None)
        assert results == []

    def test_handles_check_exception(self):
        """Should catch exceptions from individual checks and return failure result."""

        def exploding_check(_source_id, _run_record):
            raise ValueError("boom")

        with patch(
            "src.resilience.canary.CANARY_REGISTRY",
            {"test_source": [exploding_check]},
        ):
            results = run_canaries("test_source", None)

        assert len(results) == 1
        assert results[0].passed is False
        assert "boom" in results[0].message
