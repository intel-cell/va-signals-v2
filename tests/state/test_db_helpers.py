"""Tests for state intelligence DB helpers."""

import pytest
from src.state import db_helpers


class TestStateSources:
    """Tests for state source helpers."""

    def test_insert_and_get_state_source(self):
        """Test inserting and retrieving a state source."""
        source = {
            "source_id": "tx_dva_official",
            "state": "TX",
            "source_type": "official",
            "name": "Texas DVA",
            "url": "https://www.tvc.texas.gov/",
        }
        db_helpers.insert_state_source(source)  # Returns None

        # Get it back
        retrieved = db_helpers.get_state_source("tx_dva_official")
        assert retrieved is not None
        assert retrieved["source_id"] == "tx_dva_official"
        assert retrieved["state"] == "TX"
        assert retrieved["source_type"] == "official"
        assert retrieved["name"] == "Texas DVA"
        assert retrieved["url"] == "https://www.tvc.texas.gov/"
        assert retrieved["enabled"] == 1
        assert "created_at" in retrieved

    def test_insert_duplicate_source_is_idempotent(self):
        """Test that inserting a duplicate source is idempotent (no error)."""
        source = {
            "source_id": "tx_dva_official",
            "state": "TX",
            "source_type": "official",
            "name": "Texas DVA",
            "url": "https://www.tvc.texas.gov/",
        }
        db_helpers.insert_state_source(source)
        # Try again - should not raise, just skip
        db_helpers.insert_state_source(source)
        # Still only one
        retrieved = db_helpers.get_state_source("tx_dva_official")
        assert retrieved is not None

    def test_get_nonexistent_source_returns_none(self):
        """Test that getting a nonexistent source returns None."""
        result = db_helpers.get_state_source("nonexistent")
        assert result is None

    def test_get_sources_by_state(self):
        """Test getting all sources for a state."""
        sources = [
            {"source_id": "tx_1", "state": "TX", "source_type": "official", "name": "TX Source 1", "url": "https://tx1.gov"},
            {"source_id": "tx_2", "state": "TX", "source_type": "rss", "name": "TX Source 2", "url": "https://tx2.gov/rss"},
            {"source_id": "ca_1", "state": "CA", "source_type": "official", "name": "CA Source 1", "url": "https://ca1.gov"},
        ]
        for s in sources:
            db_helpers.insert_state_source(s)

        tx_sources = db_helpers.get_sources_by_state("TX")
        assert len(tx_sources) == 2
        assert all(s["state"] == "TX" for s in tx_sources)

        ca_sources = db_helpers.get_sources_by_state("CA")
        assert len(ca_sources) == 1
        assert ca_sources[0]["source_id"] == "ca_1"


class TestStateSignals:
    """Tests for state signal helpers."""

    def test_insert_and_get_state_signal(self):
        """Test inserting and retrieving a state signal."""
        # First create a source
        source = {"source_id": "tx_test", "state": "TX", "source_type": "official", "name": "Test", "url": "https://test.gov"}
        db_helpers.insert_state_source(source)

        signal = {
            "signal_id": "sig_001",
            "state": "TX",
            "source_id": "tx_test",
            "program": "healthcare",
            "title": "New Healthcare Initiative",
            "content": "Details about healthcare changes...",
            "url": "https://test.gov/news/1",
            "pub_date": "2024-01-15",
            "event_date": "2024-02-01",
        }
        db_helpers.insert_state_signal(signal)  # Returns None

        retrieved = db_helpers.get_state_signal("sig_001")
        assert retrieved is not None
        assert retrieved["signal_id"] == "sig_001"
        assert retrieved["state"] == "TX"
        assert retrieved["title"] == "New Healthcare Initiative"
        assert retrieved["program"] == "healthcare"
        assert "fetched_at" in retrieved

    def test_signal_exists(self):
        """Test checking if a signal exists."""
        source = {"source_id": "tx_test2", "state": "TX", "source_type": "official", "name": "Test2", "url": "https://test2.gov"}
        db_helpers.insert_state_source(source)

        signal = {
            "signal_id": "sig_002",
            "state": "TX",
            "source_id": "tx_test2",
            "title": "Test Signal",
            "url": "https://test2.gov/news/2",
        }
        assert db_helpers.signal_exists("sig_002") is False
        db_helpers.insert_state_signal(signal)
        assert db_helpers.signal_exists("sig_002") is True

    def test_get_signals_by_state(self):
        """Test getting signals by state."""
        source_tx = {"source_id": "tx_src", "state": "TX", "source_type": "official", "name": "TX", "url": "https://tx.gov"}
        source_ca = {"source_id": "ca_src", "state": "CA", "source_type": "official", "name": "CA", "url": "https://ca.gov"}
        db_helpers.insert_state_source(source_tx)
        db_helpers.insert_state_source(source_ca)

        signals = [
            {"signal_id": "tx_sig_1", "state": "TX", "source_id": "tx_src", "title": "TX 1", "url": "https://tx.gov/1"},
            {"signal_id": "tx_sig_2", "state": "TX", "source_id": "tx_src", "title": "TX 2", "url": "https://tx.gov/2"},
            {"signal_id": "ca_sig_1", "state": "CA", "source_id": "ca_src", "title": "CA 1", "url": "https://ca.gov/1"},
        ]
        for sig in signals:
            db_helpers.insert_state_signal(sig)

        tx_signals = db_helpers.get_signals_by_state("TX")
        assert len(tx_signals) == 2
        assert all(s["state"] == "TX" for s in tx_signals)

    def test_get_signals_by_state_with_since(self):
        """Test getting signals by state with since filter."""
        source = {"source_id": "tx_since", "state": "TX", "source_type": "official", "name": "TX", "url": "https://tx.gov"}
        db_helpers.insert_state_source(source)

        # Insert a signal
        signal = {"signal_id": "tx_since_1", "state": "TX", "source_id": "tx_since", "title": "TX 1", "url": "https://tx.gov/1"}
        db_helpers.insert_state_signal(signal)

        # Get all signals (no since)
        all_signals = db_helpers.get_signals_by_state("TX")
        assert len(all_signals) >= 1

        # Get signals since a future date (should be empty)
        future_signals = db_helpers.get_signals_by_state("TX", since="2099-01-01T00:00:00+00:00")
        assert len(future_signals) == 0

        # Get signals since a past date (should include our signal)
        past_signals = db_helpers.get_signals_by_state("TX", since="2000-01-01T00:00:00+00:00")
        assert len(past_signals) >= 1


class TestStateClassifications:
    """Tests for state classification helpers."""

    def test_insert_and_get_classification(self):
        """Test inserting and retrieving a classification."""
        # Setup
        source = {"source_id": "tx_class", "state": "TX", "source_type": "official", "name": "Test", "url": "https://test.gov"}
        db_helpers.insert_state_source(source)
        signal = {"signal_id": "sig_class", "state": "TX", "source_id": "tx_class", "title": "Test", "url": "https://test.gov/1"}
        db_helpers.insert_state_signal(signal)

        classification = {
            "signal_id": "sig_class",
            "severity": "high",
            "classification_method": "keyword",
            "keywords_matched": "budget,cut,reduction",
            "llm_reasoning": None,
        }
        db_helpers.insert_state_classification(classification)  # Returns None

        retrieved = db_helpers.get_state_classification("sig_class")
        assert retrieved is not None
        assert retrieved["severity"] == "high"
        assert retrieved["classification_method"] == "keyword"
        assert retrieved["keywords_matched"] == "budget,cut,reduction"
        assert "classified_at" in retrieved

    def test_get_unnotified_signals(self):
        """Test getting signals that haven't been notified."""
        source = {"source_id": "tx_unnotified", "state": "TX", "source_type": "official", "name": "Test", "url": "https://test.gov"}
        db_helpers.insert_state_source(source)

        # Create two signals
        signals = [
            {"signal_id": "sig_unnotified_1", "state": "TX", "source_id": "tx_unnotified", "title": "Test 1", "url": "https://test.gov/1"},
            {"signal_id": "sig_unnotified_2", "state": "TX", "source_id": "tx_unnotified", "title": "Test 2", "url": "https://test.gov/2"},
        ]
        for sig in signals:
            db_helpers.insert_state_signal(sig)

        # Classify both as high severity
        for sig_id in ["sig_unnotified_1", "sig_unnotified_2"]:
            db_helpers.insert_state_classification({
                "signal_id": sig_id,
                "severity": "high",
                "classification_method": "keyword",
            })

        # Check unnotified - both should be there
        unnotified = db_helpers.get_unnotified_signals(severity="high")
        assert len(unnotified) == 2

        # Mark one as notified
        db_helpers.mark_signal_notified("sig_unnotified_1", "slack")

        # Now only one should be unnotified
        unnotified = db_helpers.get_unnotified_signals(severity="high")
        assert len(unnotified) == 1
        assert unnotified[0]["signal_id"] == "sig_unnotified_2"


class TestStateRuns:
    """Tests for state run tracking."""

    def test_start_and_finish_run(self):
        """Test starting and finishing a run."""
        run_id = db_helpers.start_state_run(run_type="fetch", state="TX")
        assert run_id is not None
        assert isinstance(run_id, int)

        db_helpers.finish_state_run(
            run_id=run_id,
            status="SUCCESS",
            signals_found=5,
            high_severity_count=2,
        )

        runs = db_helpers.get_recent_state_runs(limit=10)
        assert len(runs) >= 1
        run = next(r for r in runs if r["id"] == run_id)
        assert run["run_type"] == "fetch"
        assert run["state"] == "TX"
        assert run["status"] == "SUCCESS"
        assert run["signals_found"] == 5
        assert run["high_severity_count"] == 2
        assert run["finished_at"] is not None

    def test_get_recent_state_runs_filtered(self):
        """Test filtering runs by state."""
        run1 = db_helpers.start_state_run(run_type="fetch", state="TX")
        db_helpers.finish_state_run(run1, "SUCCESS")
        run2 = db_helpers.start_state_run(run_type="fetch", state="CA")
        db_helpers.finish_state_run(run2, "SUCCESS")

        tx_runs = db_helpers.get_recent_state_runs(state="TX")
        ca_runs = db_helpers.get_recent_state_runs(state="CA")

        assert all(r["state"] == "TX" for r in tx_runs)
        assert all(r["state"] == "CA" for r in ca_runs)


class TestSourceHealth:
    """Tests for source health tracking."""

    def test_update_source_health_success(self):
        """Test updating source health on success."""
        source = {"source_id": "health_test", "state": "TX", "source_type": "official", "name": "Test", "url": "https://test.gov"}
        db_helpers.insert_state_source(source)

        db_helpers.update_source_health("health_test", success=True)

        health = db_helpers.get_source_health("health_test")
        assert health is not None
        assert health["consecutive_failures"] == 0
        assert health["last_success"] is not None
        assert health["last_failure"] is None

    def test_update_source_health_failure(self):
        """Test updating source health on failure."""
        source = {"source_id": "health_fail", "state": "TX", "source_type": "official", "name": "Test", "url": "https://test.gov"}
        db_helpers.insert_state_source(source)

        db_helpers.update_source_health("health_fail", success=False, error="Connection timeout")
        health = db_helpers.get_source_health("health_fail")
        assert health["consecutive_failures"] == 1
        assert health["last_error"] == "Connection timeout"

        # Second failure
        db_helpers.update_source_health("health_fail", success=False, error="Connection refused")
        health = db_helpers.get_source_health("health_fail")
        assert health["consecutive_failures"] == 2
        assert health["last_error"] == "Connection refused"

    def test_health_resets_on_success(self):
        """Test that consecutive failures reset on success."""
        source = {"source_id": "health_reset", "state": "TX", "source_type": "official", "name": "Test", "url": "https://test.gov"}
        db_helpers.insert_state_source(source)

        # Two failures
        db_helpers.update_source_health("health_reset", success=False, error="Error 1")
        db_helpers.update_source_health("health_reset", success=False, error="Error 2")
        health = db_helpers.get_source_health("health_reset")
        assert health["consecutive_failures"] == 2

        # Then success
        db_helpers.update_source_health("health_reset", success=True)
        health = db_helpers.get_source_health("health_reset")
        assert health["consecutive_failures"] == 0
        assert health["last_success"] is not None


class TestSeedDefaultSources:
    """Tests for seeding default sources."""

    def test_seed_default_sources(self):
        """Test that default sources are seeded."""
        count = db_helpers.seed_default_sources()
        assert count > 0  # Should have seeded some sources

        # Check we have sources for TX, CA, FL
        for state in ["TX", "CA", "FL"]:
            sources = db_helpers.get_sources_by_state(state)
            assert len(sources) > 0, f"No sources seeded for {state}"

    def test_seed_default_sources_idempotent(self):
        """Test that seeding is idempotent."""
        count1 = db_helpers.seed_default_sources()
        count2 = db_helpers.seed_default_sources()
        # Second call should insert 0 because all already exist
        assert count2 == 0

    def test_seed_default_sources_correct_ids(self):
        """Test that seed contains the correct source_ids per spec."""
        db_helpers.seed_default_sources()

        # Check expected source_ids exist
        expected_source_ids = [
            "tx_tvc_news",
            "tx_register",
            "ca_calvet_news",
            "ca_oal_register",
            "fl_dva_news",
            "fl_admin_register",
            "rss_texas_tribune",
            "rss_calmatters",
            "rss_florida_phoenix",
        ]
        for source_id in expected_source_ids:
            source = db_helpers.get_state_source(source_id)
            assert source is not None, f"Expected source_id {source_id} not found"
