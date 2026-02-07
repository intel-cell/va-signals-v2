"""Tests for src/run_agenda_drift.py — CLI runner for agenda drift detection."""

import json
from unittest.mock import MagicMock, patch

from src import db, run_agenda_drift

# ── helpers ──────────────────────────────────────────────────────

FAKE_MEMBERS = [
    {
        "member_id": "M001",
        "name": "Sen. Smith",
        "party": "D",
        "committee": "SVAC",
        "embedding_count": 10,
    },
    {
        "member_id": "M002",
        "name": "Rep. Jones",
        "party": "R",
        "committee": "HVAC",
        "embedding_count": 3,
    },
]

FAKE_UTTERANCES = [
    {
        "utterance_id": "U001",
        "member_id": "M001",
        "hearing_id": "H001",
        "content": "This is a test utterance about veterans benefits that is long enough to pass the minimum length filter requirement",
        "vec": [0.1, 0.2, 0.3],
    },
]

FAKE_BASELINE = {
    "member_id": "M001",
    "mu": 0.15,
    "sigma": 0.05,
    "n": 8,
}


# ── build_all_baselines ─────────────────────────────────────────


class TestBuildAllBaselines:
    @patch.object(run_agenda_drift, "build_baseline")
    @patch.object(run_agenda_drift, "get_members_with_embeddings")
    def test_builds_for_eligible_members(self, mock_members, mock_build, capsys):
        mock_members.return_value = FAKE_MEMBERS
        mock_build.return_value = {"n": 10, "mu": 0.15, "sigma": 0.05}

        stats = run_agenda_drift.build_all_baselines(min_embeddings=5)

        assert stats["total_members"] == 2
        assert stats["eligible_members"] == 1  # only M001 has >= 5
        assert stats["baselines_built"] == 1
        assert stats["skipped_insufficient"] == 1
        mock_build.assert_called_once_with("M001")

    @patch.object(run_agenda_drift, "build_baseline")
    @patch.object(run_agenda_drift, "get_members_with_embeddings")
    def test_no_eligible_members(self, mock_members, mock_build, capsys):
        mock_members.return_value = [
            {
                "member_id": "M002",
                "name": "Rep. Jones",
                "party": "R",
                "committee": "HVAC",
                "embedding_count": 2,
            },
        ]

        stats = run_agenda_drift.build_all_baselines(min_embeddings=5)

        assert stats["eligible_members"] == 0
        assert stats["skipped_insufficient"] == 1
        mock_build.assert_not_called()

    @patch.object(run_agenda_drift, "build_baseline")
    @patch.object(run_agenda_drift, "get_members_with_embeddings")
    def test_build_baseline_error(self, mock_members, mock_build, capsys):
        mock_members.return_value = [FAKE_MEMBERS[0]]  # only eligible member
        mock_build.side_effect = RuntimeError("Embedding computation failed")

        stats = run_agenda_drift.build_all_baselines(min_embeddings=5)

        assert stats["eligible_members"] == 1
        assert stats["baselines_built"] == 0
        assert len(stats["errors"]) == 1
        assert "Embedding computation" in stats["errors"][0]

    @patch.object(run_agenda_drift, "build_baseline")
    @patch.object(run_agenda_drift, "get_members_with_embeddings")
    def test_build_baseline_returns_none(self, mock_members, mock_build, capsys):
        mock_members.return_value = [FAKE_MEMBERS[0]]
        mock_build.return_value = None  # failed to build

        stats = run_agenda_drift.build_all_baselines(min_embeddings=5)

        assert stats["baselines_built"] == 0
        assert len(stats["errors"]) == 1

    @patch.object(run_agenda_drift, "build_baseline")
    @patch.object(run_agenda_drift, "get_members_with_embeddings")
    def test_empty_members(self, mock_members, mock_build, capsys):
        mock_members.return_value = []

        stats = run_agenda_drift.build_all_baselines(min_embeddings=5)

        assert stats["total_members"] == 0
        assert stats["eligible_members"] == 0
        mock_build.assert_not_called()


# ── run_detection ────────────────────────────────────────────────


class TestRunDetection:
    @patch.object(run_agenda_drift, "explain_deviation")
    @patch.object(run_agenda_drift, "detect_deviation")
    @patch.object(run_agenda_drift, "get_utterances_for_detection")
    @patch.object(db, "update_ad_deviation_note")
    @patch.object(db, "get_latest_ad_baseline")
    def test_deviation_found(
        self, mock_baseline, mock_update_note, mock_get_utts, mock_detect, mock_explain, capsys
    ):
        mock_get_utts.return_value = FAKE_UTTERANCES
        mock_baseline.return_value = FAKE_BASELINE
        mock_detect.return_value = {"id": 1, "zscore": 2.5, "cos_dist": 0.35}
        mock_explain.return_value = "Shifted from healthcare to budget policy"

        stats = run_agenda_drift.run_detection(limit=100, generate_explanations=True)

        assert stats["utterances_checked"] == 1
        assert stats["deviations_found"] == 1
        assert stats["explanations_generated"] == 1
        mock_update_note.assert_called_once_with(1, "Shifted from healthcare to budget policy")

    @patch.object(run_agenda_drift, "detect_deviation")
    @patch.object(run_agenda_drift, "get_utterances_for_detection")
    @patch.object(db, "get_latest_ad_baseline")
    def test_no_deviation(self, mock_baseline, mock_get_utts, mock_detect, capsys):
        mock_get_utts.return_value = FAKE_UTTERANCES
        mock_baseline.return_value = FAKE_BASELINE
        mock_detect.return_value = None  # no deviation

        stats = run_agenda_drift.run_detection(limit=100)

        assert stats["utterances_checked"] == 1
        assert stats["deviations_found"] == 0

    @patch.object(run_agenda_drift, "get_utterances_for_detection")
    def test_no_unchecked_utterances(self, mock_get_utts, capsys):
        mock_get_utts.return_value = []

        stats = run_agenda_drift.run_detection()

        assert stats["utterances_checked"] == 0
        output = capsys.readouterr().out
        assert "No unchecked utterances" in output

    @patch.object(run_agenda_drift, "detect_deviation")
    @patch.object(run_agenda_drift, "get_utterances_for_detection")
    @patch.object(db, "get_latest_ad_baseline")
    def test_no_baseline_skips(self, mock_baseline, mock_get_utts, mock_detect, capsys):
        mock_get_utts.return_value = FAKE_UTTERANCES
        mock_baseline.return_value = None  # no baseline for this member

        stats = run_agenda_drift.run_detection(limit=100)

        assert stats["no_baseline"] == 1
        assert stats["utterances_checked"] == 0
        mock_detect.assert_not_called()

    @patch.object(run_agenda_drift, "detect_deviation")
    @patch.object(run_agenda_drift, "get_utterances_for_detection")
    @patch.object(db, "get_latest_ad_baseline")
    def test_detection_error(self, mock_baseline, mock_get_utts, mock_detect, capsys):
        mock_get_utts.return_value = FAKE_UTTERANCES
        mock_baseline.return_value = FAKE_BASELINE
        mock_detect.side_effect = RuntimeError("Vector operation failed")

        stats = run_agenda_drift.run_detection(limit=100)

        assert len(stats["errors"]) == 1
        assert "Vector operation" in stats["errors"][0]

    @patch.object(run_agenda_drift, "explain_deviation")
    @patch.object(run_agenda_drift, "detect_deviation")
    @patch.object(run_agenda_drift, "get_utterances_for_detection")
    @patch.object(db, "update_ad_deviation_note")
    @patch.object(db, "get_latest_ad_baseline")
    def test_skip_explanations(
        self, mock_baseline, mock_update_note, mock_get_utts, mock_detect, mock_explain, capsys
    ):
        mock_get_utts.return_value = FAKE_UTTERANCES
        mock_baseline.return_value = FAKE_BASELINE
        mock_detect.return_value = {"id": 1, "zscore": 2.5, "cos_dist": 0.35}

        stats = run_agenda_drift.run_detection(limit=100, generate_explanations=False)

        assert stats["deviations_found"] == 1
        assert stats["explanations_generated"] == 0
        mock_explain.assert_not_called()


# ── backfill_explanations ────────────────────────────────────────


class TestBackfillExplanations:
    @patch.object(db, "update_ad_deviation_note")
    @patch.object(run_agenda_drift, "explain_deviation")
    @patch.object(db, "get_ad_deviations_without_notes")
    def test_backfill_success(self, mock_get_devs, mock_explain, mock_update, capsys):
        mock_get_devs.return_value = [
            {"id": 1, "member_id": "M001", "member_name": "Sen. Smith", "utterance_id": "U001"},
        ]
        mock_explain.return_value = "Policy shift explanation"

        stats = run_agenda_drift.backfill_explanations(limit=50)

        assert stats["checked"] == 1
        assert stats["generated"] == 1
        mock_update.assert_called_once_with(1, "Policy shift explanation")

    @patch.object(db, "get_ad_deviations_without_notes")
    def test_backfill_no_deviations(self, mock_get_devs, capsys):
        mock_get_devs.return_value = []

        stats = run_agenda_drift.backfill_explanations()

        assert stats["checked"] == 0
        output = capsys.readouterr().out
        assert "No deviations need explanations" in output

    @patch.object(run_agenda_drift, "explain_deviation")
    @patch.object(db, "get_ad_deviations_without_notes")
    def test_backfill_explanation_fails(self, mock_get_devs, mock_explain, capsys):
        mock_get_devs.return_value = [
            {"id": 1, "member_id": "M001", "member_name": "Sen. Smith", "utterance_id": "U001"},
        ]
        mock_explain.return_value = None  # explanation failed

        stats = run_agenda_drift.backfill_explanations()

        assert stats["checked"] == 1
        assert stats["generated"] == 0
        assert len(stats["errors"]) == 1

    @patch.object(run_agenda_drift, "explain_deviation")
    @patch.object(db, "get_ad_deviations_without_notes")
    def test_backfill_exception(self, mock_get_devs, mock_explain, capsys):
        mock_get_devs.return_value = [
            {"id": 1, "member_id": "M001", "member_name": "Sen. Smith", "utterance_id": "U001"},
        ]
        mock_explain.side_effect = RuntimeError("LLM API timeout")

        stats = run_agenda_drift.backfill_explanations()

        assert len(stats["errors"]) == 1
        assert "LLM API timeout" in stats["errors"][0]


# ── get_members_with_embeddings ──────────────────────────────────


class TestGetMembersWithEmbeddings:
    @patch.object(db, "execute")
    @patch.object(db, "connect")
    def test_returns_members(self, mock_connect, mock_execute):
        mock_con = MagicMock()
        mock_connect.return_value = mock_con
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("M001", "Sen. Smith", "D", "SVAC", 10),
        ]
        mock_execute.return_value = mock_cur

        result = run_agenda_drift.get_members_with_embeddings()

        assert len(result) == 1
        assert result[0]["member_id"] == "M001"
        assert result[0]["embedding_count"] == 10
        mock_con.close.assert_called_once()

    @patch.object(db, "execute")
    @patch.object(db, "connect")
    def test_returns_empty(self, mock_connect, mock_execute):
        mock_con = MagicMock()
        mock_connect.return_value = mock_con
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_execute.return_value = mock_cur

        result = run_agenda_drift.get_members_with_embeddings()

        assert result == []


# ── get_utterances_for_detection ─────────────────────────────────


class TestGetUtterancesForDetection:
    @patch.object(db, "execute")
    @patch.object(db, "connect")
    def test_returns_utterances(self, mock_connect, mock_execute):
        mock_con = MagicMock()
        mock_connect.return_value = mock_con
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("U001", "M001", "H001", "Test content", json.dumps([0.1, 0.2])),
        ]
        mock_execute.return_value = mock_cur

        result = run_agenda_drift.get_utterances_for_detection()

        assert len(result) == 1
        assert result[0]["utterance_id"] == "U001"
        assert result[0]["vec"] == [0.1, 0.2]

    @patch.object(db, "execute")
    @patch.object(db, "connect")
    def test_with_member_filter(self, mock_connect, mock_execute):
        mock_con = MagicMock()
        mock_connect.return_value = mock_con
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_execute.return_value = mock_cur

        result = run_agenda_drift.get_utterances_for_detection(member_id="M001")

        assert result == []
        # Verify the query included member_id param
        call_args = mock_execute.call_args
        assert (
            "member_id" in call_args[0][1]
            if len(call_args[0]) > 1
            else "member_id"
            in call_args[1].get("params", call_args[0][2] if len(call_args[0]) > 2 else {})
        )


# ── get_baseline_stats ───────────────────────────────────────────


class TestGetBaselineStats:
    @patch.object(db, "execute")
    @patch.object(db, "connect")
    def test_returns_stats(self, mock_connect, mock_execute):
        mock_con = MagicMock()
        mock_connect.return_value = mock_con
        mock_cur = MagicMock()
        mock_cur.fetchone = MagicMock(side_effect=[(5,), (10,), (3,), (1,)])
        mock_execute.return_value = mock_cur

        result = run_agenda_drift.get_baseline_stats()

        assert result["members_with_baselines"] == 5
        assert result["total_baselines"] == 10
        assert result["total_deviations"] == 3
        assert result["significant_deviations"] == 1


# ── print_summary ────────────────────────────────────────────────


class TestPrintSummary:
    @patch.object(run_agenda_drift, "get_recent_deviations")
    @patch.object(run_agenda_drift, "get_baseline_stats")
    @patch.object(db, "execute")
    @patch.object(db, "connect")
    def test_prints_summary(self, mock_connect, mock_execute, mock_bl_stats, mock_recent, capsys):
        mock_con = MagicMock()
        mock_connect.return_value = mock_con
        mock_cur = MagicMock()
        mock_cur.fetchone = MagicMock(side_effect=[(100,), (500,), (450,)])
        mock_execute.return_value = mock_cur
        mock_bl_stats.return_value = {
            "members_with_baselines": 8,
            "total_baselines": 8,
            "total_deviations": 5,
            "significant_deviations": 2,
        }
        mock_recent.return_value = [
            {"member_name": "Sen. Smith", "zscore": 2.5, "hearing_id": "H001"},
        ]

        run_agenda_drift.print_summary()

        output = capsys.readouterr().out
        assert "AGENDA DRIFT DETECTION" in output
        assert "Members:" in output
        assert "Recent Deviations:" in output


# ── main (argument parsing) ──────────────────────────────────────


class TestMainArgParsing:
    @patch.object(run_agenda_drift, "print_summary")
    @patch.object(run_agenda_drift, "build_all_baselines")
    @patch.object(run_agenda_drift, "run_detection")
    @patch.object(db, "init_db")
    def test_summary_flag(self, mock_init, mock_detect, mock_build, mock_summary):
        with patch("sys.argv", ["prog", "--summary"]):
            run_agenda_drift.main.__wrapped__()
        mock_summary.assert_called_once()
        mock_build.assert_not_called()
        mock_detect.assert_not_called()

    @patch.object(run_agenda_drift, "print_summary")
    @patch.object(run_agenda_drift, "build_all_baselines")
    @patch.object(run_agenda_drift, "run_detection")
    @patch.object(db, "init_db")
    def test_build_baselines_flag(self, mock_init, mock_detect, mock_build, mock_summary):
        mock_build.return_value = {
            "total_members": 2,
            "eligible_members": 1,
            "baselines_built": 1,
            "skipped_insufficient": 1,
            "errors": [],
        }
        with patch("sys.argv", ["prog", "--build-baselines"]):
            run_agenda_drift.main.__wrapped__()
        mock_build.assert_called_once()
        mock_detect.assert_not_called()

    @patch.object(run_agenda_drift, "print_summary")
    @patch.object(run_agenda_drift, "build_all_baselines")
    @patch.object(run_agenda_drift, "run_detection")
    @patch.object(db, "init_db")
    def test_detect_flag(self, mock_init, mock_detect, mock_build, mock_summary):
        mock_detect.return_value = {
            "utterances_checked": 5,
            "deviations_found": 1,
            "explanations_generated": 1,
            "no_baseline": 0,
            "errors": [],
        }
        with patch("sys.argv", ["prog", "--detect"]):
            run_agenda_drift.main.__wrapped__()
        mock_detect.assert_called_once()
        mock_build.assert_not_called()

    @patch.object(run_agenda_drift, "print_summary")
    @patch.object(run_agenda_drift, "build_all_baselines")
    @patch.object(run_agenda_drift, "run_detection")
    @patch.object(db, "init_db")
    def test_all_flag(self, mock_init, mock_detect, mock_build, mock_summary):
        mock_build.return_value = {
            "total_members": 2,
            "eligible_members": 1,
            "baselines_built": 1,
            "skipped_insufficient": 1,
            "errors": [],
        }
        mock_detect.return_value = {
            "utterances_checked": 5,
            "deviations_found": 0,
            "explanations_generated": 0,
            "no_baseline": 0,
            "errors": [],
        }
        with patch("sys.argv", ["prog", "--all"]):
            run_agenda_drift.main.__wrapped__()
        mock_build.assert_called_once()
        mock_detect.assert_called_once()

    @patch.object(run_agenda_drift, "print_summary")
    @patch.object(run_agenda_drift, "build_all_baselines")
    @patch.object(run_agenda_drift, "run_detection")
    @patch.object(db, "init_db")
    def test_default_runs_all(self, mock_init, mock_detect, mock_build, mock_summary):
        """When no flags given, defaults to --all."""
        mock_build.return_value = {
            "total_members": 0,
            "eligible_members": 0,
            "baselines_built": 0,
            "skipped_insufficient": 0,
            "errors": [],
        }
        mock_detect.return_value = {
            "utterances_checked": 0,
            "deviations_found": 0,
            "explanations_generated": 0,
            "no_baseline": 0,
            "errors": [],
        }
        with patch("sys.argv", ["prog"]):
            run_agenda_drift.main.__wrapped__()
        mock_build.assert_called_once()
        mock_detect.assert_called_once()

    @patch.object(run_agenda_drift, "print_summary")
    @patch.object(run_agenda_drift, "backfill_explanations")
    @patch.object(db, "init_db")
    def test_backfill_flag(self, mock_init, mock_backfill, mock_summary):
        mock_backfill.return_value = {"checked": 3, "generated": 2, "errors": []}
        with patch("sys.argv", ["prog", "--backfill-explanations"]):
            run_agenda_drift.main.__wrapped__()
        mock_backfill.assert_called_once()
        mock_summary.assert_called()


# ── get_recent_deviations ────────────────────────────────────────


class TestGetRecentDeviations:
    @patch.object(db, "get_ad_deviation_events")
    def test_delegates_to_db(self, mock_get_events):
        mock_get_events.return_value = [{"id": 1}]

        result = run_agenda_drift.get_recent_deviations(limit=5)

        assert result == [{"id": 1}]
        mock_get_events.assert_called_once_with(limit=5, min_zscore=0)
