"""Tests for state intelligence runner orchestrator."""

from datetime import UTC
from unittest.mock import MagicMock, Mock, patch

from src.state import db_helpers
from src.state.classify import ClassificationResult
from src.state.common import RawSignal
from src.state.runner import (
    MONITORED_STATES,
    _classify_signal,
    _get_run_type_from_hour,
    _is_official_source,
    _process_single_state,
)


class TestIsOfficialSource:
    """Tests for official source detection."""

    def test_tvc_news_is_official(self):
        """TX TVC news is official."""
        assert _is_official_source("tx_tvc_news") is True

    def test_calvet_news_is_official(self):
        """CA CalVet news is official."""
        assert _is_official_source("ca_calvet_news") is True

    def test_dva_news_is_official(self):
        """FL DVA news is official."""
        assert _is_official_source("fl_dva_news") is True

    def test_register_sources_are_official(self):
        """Register sources are official."""
        assert _is_official_source("tx_register") is True
        assert _is_official_source("ca_oal_register") is True
        assert _is_official_source("fl_admin_register") is True

    def test_newsapi_is_not_official(self):
        """NewsAPI source is not official."""
        assert _is_official_source("newsapi_tx") is False

    def test_rss_is_not_official(self):
        """RSS source is not official."""
        assert _is_official_source("rss_tx") is False


class TestClassifySignal:
    """Tests for classification routing."""

    def test_official_source_uses_keyword_classification(self):
        """Official sources use keyword classification."""
        signal = RawSignal(
            url="https://tvc.texas.gov/news/1",
            title="Budget cuts announced",
            source_id="tx_tvc_news",
            state="TX",
            content="The program has been suspended.",
        )

        result = _classify_signal(signal)

        assert result.method == "keyword"
        assert result.severity == "high"  # "suspended" is high severity keyword

    def test_news_source_routes_to_llm(self):
        """News sources route to LLM classification."""
        signal = RawSignal(
            url="https://news.example.com/article",
            title="Veterans healthcare article",
            source_id="newsapi_tx",
            state="TX",
            content="General news content.",
        )

        # Mock the LLM call to verify it's called for news sources
        with patch("src.state.runner.classify_by_llm") as mock_llm:
            mock_llm.return_value = ClassificationResult(
                severity="low", method="llm", llm_reasoning="Test reason"
            )
            result = _classify_signal(signal)

            assert mock_llm.called
            assert result.method == "llm"


class TestRunStateMonitor:
    """Tests for main orchestration function."""

    def _create_mock_sources(self):
        """Create mock source instances."""
        # TX Official
        tx_instance = Mock()
        tx_instance.source_id = "tx_tvc_news"
        tx_instance.fetch.return_value = [
            RawSignal(
                url="https://tx.gov/news/1",
                title="TX official news",
                source_id="tx_tvc_news",
                state="TX",
            )
        ]

        # CA Official
        ca_instance = Mock()
        ca_instance.source_id = "ca_calvet_news"
        ca_instance.fetch.return_value = [
            RawSignal(
                url="https://ca.gov/news/1",
                title="CA official news",
                source_id="ca_calvet_news",
                state="CA",
            )
        ]

        # FL Official
        fl_instance = Mock()
        fl_instance.source_id = "fl_dva_news"
        fl_instance.fetch.return_value = [
            RawSignal(
                url="https://fl.gov/news/1",
                title="FL official news",
                source_id="fl_dva_news",
                state="FL",
            )
        ]

        # NewsAPI
        newsapi_instance = Mock()
        newsapi_instance.source_id = "newsapi_tx"
        newsapi_instance.fetch.return_value = []

        # RSS
        rss_instance = Mock()
        rss_instance.source_id = "rss_tx"
        rss_instance.fetch.return_value = []

        return {
            "tx": tx_instance,
            "ca": ca_instance,
            "fl": fl_instance,
            "newsapi": newsapi_instance,
            "rss": rss_instance,
        }

    def _get_official_source_mock(self, mocks):
        """Create a mock _get_official_source function that returns mock classes."""

        def mock_get_official_source(state):
            source_map = {
                "TX": Mock(return_value=mocks["tx"]),
                "CA": Mock(return_value=mocks["ca"]),
                "FL": Mock(return_value=mocks["fl"]),
            }
            return source_map.get(state)

        return mock_get_official_source

    def test_successful_run_records_to_state_runs(self):
        """Test that a successful run is recorded in state_runs table."""
        mocks = self._create_mock_sources()

        with (
            patch("src.state.runner._get_official_source") as mock_get_official,
            patch("src.state.runner.NewsAPISource", return_value=mocks["newsapi"]),
            patch("src.state.runner.RSSSource", return_value=mocks["rss"]),
        ):
            mock_get_official.return_value = Mock(return_value=mocks["tx"])

            from src.state.runner import run_state_monitor

            summary = run_state_monitor(run_type="morning", state="TX", dry_run=True)

            assert summary["run_id"] is not None
            assert summary["status"] == "SUCCESS"
            assert summary["run_type"] == "morning"
            assert summary["state"] == "TX"

            # Verify run was recorded in DB
            runs = db_helpers.get_recent_state_runs(state="TX", limit=5)
            assert len(runs) >= 1
            latest_run = runs[0]
            assert latest_run["id"] == summary["run_id"]
            assert latest_run["status"] == "SUCCESS"
            assert latest_run["finished_at"] is not None

    def test_single_state_filtering_works(self):
        """Test that specifying a single state only processes that state."""
        mocks = self._create_mock_sources()

        # Track which states were requested
        states_requested = []

        def mock_get_official_source(state):
            states_requested.append(state)
            source_map = {
                "TX": Mock(return_value=mocks["tx"]),
                "CA": Mock(return_value=mocks["ca"]),
                "FL": Mock(return_value=mocks["fl"]),
            }
            return source_map.get(state)

        with (
            patch("src.state.runner._get_official_source", side_effect=mock_get_official_source),
            patch("src.state.runner.NewsAPISource", return_value=mocks["newsapi"]),
            patch("src.state.runner.RSSSource", return_value=mocks["rss"]),
        ):
            from src.state.runner import run_state_monitor

            summary = run_state_monitor(run_type="morning", state="TX", dry_run=True)

            # Only TX should have been requested
            assert states_requested == ["TX"]
            assert summary["state"] == "TX"

    def test_all_states_processed_when_none_specified(self):
        """Test that all states are processed when no state is specified."""
        mocks = self._create_mock_sources()

        # Track which states were requested
        states_requested = []

        def mock_get_official_source(state):
            states_requested.append(state)
            source_map = {
                "TX": Mock(return_value=mocks["tx"]),
                "CA": Mock(return_value=mocks["ca"]),
                "FL": Mock(return_value=mocks["fl"]),
            }
            return source_map.get(state)

        with (
            patch("src.state.runner._get_official_source", side_effect=mock_get_official_source),
            patch("src.state.runner.NewsAPISource", return_value=mocks["newsapi"]),
            patch("src.state.runner.RSSSource", return_value=mocks["rss"]),
        ):
            from src.state.runner import run_state_monitor

            summary = run_state_monitor(run_type="morning", state=None, dry_run=True)

            # All states should have been requested
            assert set(states_requested) == {
                "TX",
                "CA",
                "FL",
                "PA",
                "OH",
                "NY",
                "NC",
                "GA",
                "VA",
                "AZ",
            }
            assert summary["state"] is None

    def test_dry_run_skips_notifications(self):
        """Test that dry_run=True skips Slack notifications."""
        mocks = self._create_mock_sources()
        # Create a high-severity signal
        mocks["tx"].fetch.return_value = [
            RawSignal(
                url="https://tx.gov/news/high-severity",
                title="Program suspended immediately",  # High severity keyword
                source_id="tx_tvc_news",
                state="TX",
                content="The program has been suspended.",
            )
        ]

        with (
            patch(
                "src.state.runner._get_official_source", return_value=Mock(return_value=mocks["tx"])
            ),
            patch("src.state.runner.NewsAPISource", return_value=mocks["newsapi"]),
            patch("src.state.runner.RSSSource", return_value=mocks["rss"]),
            patch("src.state.runner._send_email") as mock_email,
        ):
            from src.state.runner import run_state_monitor

            summary = run_state_monitor(run_type="morning", state="TX", dry_run=True)

            # Email should NOT have been called in dry_run mode
            mock_email.assert_not_called()

            # But we should have found high severity signals
            assert summary["high_severity_count"] >= 1
            assert summary["dry_run"] is True

    def test_notifications_sent_when_not_dry_run(self):
        """Test that notifications are sent when dry_run=False."""
        mocks = self._create_mock_sources()
        # Create a high-severity signal
        mocks["tx"].fetch.return_value = [
            RawSignal(
                url="https://tx.gov/news/notify-test",
                title="Program terminated",  # High severity keyword
                source_id="tx_tvc_news",
                state="TX",
                content="The program has been terminated.",
            )
        ]

        with (
            patch(
                "src.state.runner._get_official_source", return_value=Mock(return_value=mocks["tx"])
            ),
            patch("src.state.runner.NewsAPISource", return_value=mocks["newsapi"]),
            patch("src.state.runner.RSSSource", return_value=mocks["rss"]),
            patch("src.state.runner._send_email", return_value=True) as mock_email,
            patch("src.state.runner.email_configured", return_value=True),
        ):
            from src.state.runner import run_state_monitor

            summary = run_state_monitor(run_type="morning", state="TX", dry_run=False)

            # Email should have been called for high severity
            assert mock_email.called
            assert summary["high_severity_count"] >= 1

    def test_partial_source_failure_continues(self):
        """Test that if one source fails, processing continues with others."""
        mocks = self._create_mock_sources()
        # Make TX official source fail
        mocks["tx"].fetch.side_effect = Exception("Connection error")

        with (
            patch(
                "src.state.runner._get_official_source", return_value=Mock(return_value=mocks["tx"])
            ),
            patch("src.state.runner.NewsAPISource", return_value=mocks["newsapi"]),
            patch("src.state.runner.RSSSource", return_value=mocks["rss"]),
        ):
            from src.state.runner import run_state_monitor

            summary = run_state_monitor(run_type="morning", state="TX", dry_run=True)

            # Status should be PARTIAL (some sources succeeded, some failed)
            assert summary["status"] in ["PARTIAL", "SUCCESS"]  # SUCCESS if NewsAPI/RSS work
            assert summary["source_failures"] >= 1
            assert len(summary["errors"]) >= 1

    def test_all_sources_fail_returns_error_status(self):
        """Test that if ALL sources fail, status is ERROR."""
        mocks = self._create_mock_sources()
        # Make all sources fail for TX
        mocks["tx"].fetch.side_effect = Exception("TX official error")
        mocks["newsapi"].fetch.side_effect = Exception("NewsAPI error")
        mocks["rss"].fetch.side_effect = Exception("RSS error")

        with (
            patch(
                "src.state.runner._get_official_source", return_value=Mock(return_value=mocks["tx"])
            ),
            patch("src.state.runner.NewsAPISource", return_value=mocks["newsapi"]),
            patch("src.state.runner.RSSSource", return_value=mocks["rss"]),
        ):
            from src.state.runner import run_state_monitor

            summary = run_state_monitor(run_type="morning", state="TX", dry_run=True)

            # Status should be ERROR when all sources fail
            assert summary["status"] == "ERROR"
            assert summary["source_successes"] == 0
            assert summary["source_failures"] >= 3

    def test_classification_routing_official_vs_news(self):
        """Test that official sources use keyword classification and news uses LLM."""
        mocks = self._create_mock_sources()
        # Official source
        mocks["tx"].fetch.return_value = [
            RawSignal(
                url="https://tx.gov/official-test",
                title="Official announcement",
                source_id="tx_tvc_news",
                state="TX",
            )
        ]

        # NewsAPI source
        mocks["newsapi"].fetch.return_value = [
            RawSignal(
                url="https://news.com/news-test",
                title="News article",
                source_id="newsapi_tx",
                state="TX",
            )
        ]

        with (
            patch(
                "src.state.runner._get_official_source", return_value=Mock(return_value=mocks["tx"])
            ),
            patch("src.state.runner.NewsAPISource", return_value=mocks["newsapi"]),
            patch("src.state.runner.RSSSource", return_value=mocks["rss"]),
            patch("src.state.runner.classify_by_keywords") as mock_keyword,
            patch("src.state.runner.classify_by_llm") as mock_llm,
        ):
            # Set up return values
            mock_keyword.return_value = ClassificationResult(severity="low", method="keyword")
            mock_llm.return_value = ClassificationResult(severity="low", method="llm")

            from src.state.runner import run_state_monitor

            run_state_monitor(run_type="morning", state="TX", dry_run=True)

            # Official source should use keyword classification
            assert mock_keyword.called
            # News source should use LLM classification
            assert mock_llm.called

    def test_signals_deduplicated_by_url(self):
        """Test that duplicate signals (same URL) are deduplicated."""
        mocks = self._create_mock_sources()
        # Same URL from multiple sources
        same_url = "https://shared-news.com/article"

        mocks["tx"].fetch.return_value = [
            RawSignal(
                url=same_url,
                title="Title from TX official",
                source_id="tx_tvc_news",
                state="TX",
            )
        ]

        mocks["newsapi"].fetch.return_value = [
            RawSignal(
                url=same_url,
                title="Title from NewsAPI",
                source_id="newsapi_tx",
                state="TX",
            )
        ]

        with (
            patch(
                "src.state.runner._get_official_source", return_value=Mock(return_value=mocks["tx"])
            ),
            patch("src.state.runner.NewsAPISource", return_value=mocks["newsapi"]),
            patch("src.state.runner.RSSSource", return_value=mocks["rss"]),
        ):
            from src.state.runner import run_state_monitor

            summary = run_state_monitor(run_type="morning", state="TX", dry_run=True)

            # Should only have 1 new signal (deduplicated)
            assert summary["new_signals"] == 1

    def test_source_health_updated_on_success(self):
        """Test that source health is updated on successful fetch."""
        mocks = self._create_mock_sources()

        with (
            patch(
                "src.state.runner._get_official_source", return_value=Mock(return_value=mocks["tx"])
            ),
            patch("src.state.runner.NewsAPISource", return_value=mocks["newsapi"]),
            patch("src.state.runner.RSSSource", return_value=mocks["rss"]),
        ):
            from src.state.runner import run_state_monitor

            run_state_monitor(run_type="morning", state="TX", dry_run=True)

            # Check that health was recorded for TX official source
            health = db_helpers.get_source_health("tx_tvc_news")
            assert health is not None
            assert health["consecutive_failures"] == 0
            assert health["last_success"] is not None

    def test_source_health_updated_on_failure(self):
        """Test that source health is updated on failed fetch."""
        mocks = self._create_mock_sources()
        # Make TX official fail
        mocks["tx"].fetch.side_effect = Exception("Test error")

        with (
            patch(
                "src.state.runner._get_official_source", return_value=Mock(return_value=mocks["tx"])
            ),
            patch("src.state.runner.NewsAPISource", return_value=mocks["newsapi"]),
            patch("src.state.runner.RSSSource", return_value=mocks["rss"]),
        ):
            from src.state.runner import run_state_monitor

            run_state_monitor(run_type="morning", state="TX", dry_run=True)

            # Check that health was recorded with failure
            health = db_helpers.get_source_health("tx_tvc_news")
            assert health is not None
            assert health["consecutive_failures"] >= 1


class TestGetRunTypeFromHour:
    """Tests for run type determination based on hour."""

    def test_morning_hours(self):
        """Test that hours 6-13 UTC are morning."""
        from datetime import datetime, timezone
        from unittest.mock import patch

        for hour in [6, 7, 8, 9, 10, 11, 12, 13]:
            with patch("src.state.runner.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2026, 1, 21, hour, 0, 0, tzinfo=UTC)
                mock_dt.timezone = timezone
                result = _get_run_type_from_hour()
                assert result == "morning", f"Hour {hour} should be morning"

    def test_evening_hours(self):
        """Test that hours 14-23 and 0-5 UTC are evening."""
        from datetime import datetime, timezone
        from unittest.mock import patch

        for hour in [14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5]:
            with patch("src.state.runner.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2026, 1, 21, hour, 0, 0, tzinfo=UTC)
                mock_dt.timezone = timezone
                result = _get_run_type_from_hour()
                assert result == "evening", f"Hour {hour} should be evening"


class TestRunnerIntegration:
    """Integration tests for the runner."""

    def test_new_signals_stored_in_database(self):
        """Test that new signals are stored in the database."""
        # TX Official
        tx_instance = Mock()
        tx_instance.source_id = "tx_tvc_news"
        tx_instance.fetch.return_value = [
            RawSignal(
                url="https://tx.gov/integration-test",
                title="Integration test signal",
                source_id="tx_tvc_news",
                state="TX",
                content="Test content",
                pub_date="2026-01-21",
            )
        ]

        # NewsAPI
        newsapi_instance = Mock()
        newsapi_instance.source_id = "newsapi_tx"
        newsapi_instance.fetch.return_value = []

        # RSS
        rss_instance = Mock()
        rss_instance.source_id = "rss_tx"
        rss_instance.fetch.return_value = []

        with (
            patch(
                "src.state.runner._get_official_source", return_value=Mock(return_value=tx_instance)
            ),
            patch("src.state.runner.NewsAPISource", return_value=newsapi_instance),
            patch("src.state.runner.RSSSource", return_value=rss_instance),
        ):
            from src.state.runner import run_state_monitor

            summary = run_state_monitor(run_type="morning", state="TX", dry_run=True)

            assert summary["new_signals"] == 1

            # Verify signal is in database
            from src.state.common import generate_signal_id

            sig_id = generate_signal_id("https://tx.gov/integration-test")
            signal = db_helpers.get_state_signal(sig_id)
            assert signal is not None
            assert signal["title"] == "Integration test signal"
            assert signal["state"] == "TX"

            # Verify classification is in database
            classification = db_helpers.get_state_classification(sig_id)
            assert classification is not None
            assert classification["severity"] in ["high", "medium", "low", "noise"]


class TestProcessSingleState:
    """Tests for _process_single_state helper (extracted per-state logic)."""

    def test_returns_result_dict_with_expected_keys(self):
        """_process_single_state returns a dict with all counter keys."""
        tx_instance = Mock()
        tx_instance.source_id = "tx_tvc_news"
        tx_instance.fetch.return_value = [
            RawSignal(
                url="https://tx.gov/pss-test-1",
                title="PSS test signal",
                source_id="tx_tvc_news",
                state="TX",
            )
        ]

        newsapi_instance = Mock()
        newsapi_instance.source_id = "newsapi_tx"
        newsapi_instance.fetch.return_value = []

        rss_instance = Mock()
        rss_instance.source_id = "rss_tx"
        rss_instance.fetch.return_value = []

        with (
            patch(
                "src.state.runner._get_official_source", return_value=Mock(return_value=tx_instance)
            ),
            patch("src.state.runner.NewsAPISource", return_value=newsapi_instance),
            patch("src.state.runner.RSSSource", return_value=rss_instance),
        ):
            result = _process_single_state("TX", dry_run=True)

            expected_keys = {
                "total_signals_found",
                "high_severity_count",
                "new_signals_count",
                "source_successes",
                "source_failures",
                "errors",
            }
            assert set(result.keys()) == expected_keys
            assert isinstance(result["errors"], list)
            assert result["source_successes"] >= 1

    def test_source_failure_counted_locally(self):
        """Source failures are counted in the local result dict."""
        tx_instance = Mock()
        tx_instance.source_id = "tx_tvc_news"
        tx_instance.fetch.side_effect = Exception("Connection failed")

        newsapi_instance = Mock()
        newsapi_instance.source_id = "newsapi_tx"
        newsapi_instance.fetch.return_value = []

        rss_instance = Mock()
        rss_instance.source_id = "rss_tx"
        rss_instance.fetch.return_value = []

        with (
            patch(
                "src.state.runner._get_official_source", return_value=Mock(return_value=tx_instance)
            ),
            patch("src.state.runner.NewsAPISource", return_value=newsapi_instance),
            patch("src.state.runner.RSSSource", return_value=rss_instance),
        ):
            result = _process_single_state("TX", dry_run=True)

            assert result["source_failures"] >= 1
            assert len(result["errors"]) >= 1

    def test_high_severity_counted_locally(self):
        """High severity signals are counted in the local result dict."""
        tx_instance = Mock()
        tx_instance.source_id = "tx_tvc_news"
        tx_instance.fetch.return_value = [
            RawSignal(
                url="https://tx.gov/pss-high-sev",
                title="Program suspended immediately",
                source_id="tx_tvc_news",
                state="TX",
                content="The program has been suspended.",
            )
        ]

        newsapi_instance = Mock()
        newsapi_instance.source_id = "newsapi_tx"
        newsapi_instance.fetch.return_value = []

        rss_instance = Mock()
        rss_instance.source_id = "rss_tx"
        rss_instance.fetch.return_value = []

        with (
            patch(
                "src.state.runner._get_official_source", return_value=Mock(return_value=tx_instance)
            ),
            patch("src.state.runner.NewsAPISource", return_value=newsapi_instance),
            patch("src.state.runner.RSSSource", return_value=rss_instance),
        ):
            result = _process_single_state("TX", dry_run=True)

            assert result["high_severity_count"] >= 1
            assert result["new_signals_count"] >= 1


class TestParallelExecution:
    """Tests that run_state_monitor uses ThreadPoolExecutor for multi-state runs."""

    def test_threadpool_used_for_multiple_states(self):
        """ThreadPoolExecutor is used when processing multiple states."""
        newsapi_instance = Mock()
        newsapi_instance.source_id = "newsapi_tx"
        newsapi_instance.fetch.return_value = []

        rss_instance = Mock()
        rss_instance.source_id = "rss_tx"
        rss_instance.fetch.return_value = []

        with (
            patch("src.state.runner._get_official_source", return_value=None),
            patch("src.state.runner.NewsAPISource", return_value=newsapi_instance),
            patch("src.state.runner.RSSSource", return_value=rss_instance),
            patch("src.state.runner.ThreadPoolExecutor") as mock_executor_cls,
        ):
            # Set up the mock executor context manager
            mock_executor = MagicMock()
            mock_executor_cls.return_value.__enter__ = Mock(return_value=mock_executor)
            mock_executor_cls.return_value.__exit__ = Mock(return_value=False)

            # Make executor.submit return futures with proper results
            mock_future = Mock()
            mock_future.result.return_value = {
                "total_signals_found": 0,
                "high_severity_count": 0,
                "new_signals_count": 0,
                "source_successes": 1,
                "source_failures": 0,
                "errors": [],
            }
            mock_executor.submit.return_value = mock_future

            from src.state.runner import run_state_monitor

            run_state_monitor(run_type="morning", state=None, dry_run=True)

            # ThreadPoolExecutor should have been created with max_workers capped at 6
            mock_executor_cls.assert_called_once()
            call_kwargs = mock_executor_cls.call_args
            max_workers = call_kwargs[1].get("max_workers") or call_kwargs[0][0]
            assert max_workers == 6  # 10 states capped at 6

    def test_single_state_does_not_use_threadpool(self):
        """Single-state run should NOT use ThreadPoolExecutor (no overhead)."""
        tx_instance = Mock()
        tx_instance.source_id = "tx_tvc_news"
        tx_instance.fetch.return_value = []

        newsapi_instance = Mock()
        newsapi_instance.source_id = "newsapi_tx"
        newsapi_instance.fetch.return_value = []

        rss_instance = Mock()
        rss_instance.source_id = "rss_tx"
        rss_instance.fetch.return_value = []

        with (
            patch(
                "src.state.runner._get_official_source", return_value=Mock(return_value=tx_instance)
            ),
            patch("src.state.runner.NewsAPISource", return_value=newsapi_instance),
            patch("src.state.runner.RSSSource", return_value=rss_instance),
            patch("src.state.runner.ThreadPoolExecutor") as mock_executor_cls,
        ):
            from src.state.runner import run_state_monitor

            run_state_monitor(run_type="morning", state="TX", dry_run=True)

            # ThreadPoolExecutor should NOT be used for a single state
            mock_executor_cls.assert_not_called()

    def test_results_aggregated_correctly_across_states(self):
        """Results from parallel state processing are aggregated correctly."""
        call_count = {"n": 0}

        def mock_process(st, dry_run=False):
            call_count["n"] += 1
            return {
                "total_signals_found": 2,
                "high_severity_count": 1,
                "new_signals_count": 1,
                "source_successes": 3,
                "source_failures": 0,
                "errors": [],
            }

        with patch("src.state.runner._process_single_state", side_effect=mock_process):
            from src.state.runner import run_state_monitor

            summary = run_state_monitor(run_type="morning", state=None, dry_run=True)

            # All 10 states should have been processed
            assert call_count["n"] == 10
            # Aggregated: 10 states * 2 signals each = 20
            assert summary["total_signals_found"] == 20
            assert summary["new_signals"] == 10
            assert summary["high_severity_count"] == 10
            assert summary["source_successes"] == 30

    def test_results_deterministic_order(self):
        """Results should be aggregated in deterministic state order."""

        def mock_process(st, dry_run=False):
            return {
                "total_signals_found": 1,
                "high_severity_count": 0,
                "new_signals_count": 0,
                "source_successes": 1,
                "source_failures": 0,
                "errors": [f"error-from-{st}"],
            }

        with patch("src.state.runner._process_single_state", side_effect=mock_process):
            from src.state.runner import run_state_monitor

            summary = run_state_monitor(run_type="morning", state=None, dry_run=True)

            # Errors should be in MONITORED_STATES order (deterministic)
            expected_errors = [f"error-from-{st}" for st in MONITORED_STATES]
            assert summary["errors"] == expected_errors
