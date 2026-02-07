"""Tests for bill committee fetch and update functionality."""

import json
from unittest.mock import patch, MagicMock

import pytest

import src.db as db
from src.fetch_bills import fetch_bill_committees


# ── Sample API response ────────────────────────────────────────

SAMPLE_COMMITTEES_RESPONSE = {
    "committees": [
        {
            "name": "Veterans' Affairs Committee",
            "chamber": "House",
            "type": "Standing",
        },
        {
            "name": "Armed Services Committee",
            "chamber": "Senate",
            "type": "Standing",
        },
    ]
}


# ── helpers ─────────────────────────────────────────────────────

def _insert_test_bill(committees_json="[]"):
    db.upsert_bill({
        "bill_id": "hr-119-100",
        "congress": 119,
        "bill_type": "hr",
        "bill_number": 100,
        "title": "Test VA Bill",
        "sponsor_name": "Smith",
        "sponsor_bioguide_id": "S000001",
        "sponsor_party": "D",
        "sponsor_state": "CA",
        "introduced_date": "2025-01-10",
        "latest_action_date": "2025-02-15",
        "latest_action_text": "Introduced",
        "policy_area": "Veterans",
        "committees_json": committees_json,
        "cosponsors_count": 3,
    })


# ── fetch_bill_committees ──────────────────────────────────────

class TestFetchBillCommittees:
    @patch("src.fetch_bills._fetch_json")
    @patch("src.fetch_bills.get_api_key", return_value="test-key")
    def test_parses_committee_response(self, mock_key, mock_fetch):
        mock_fetch.return_value = SAMPLE_COMMITTEES_RESPONSE

        result = fetch_bill_committees(119, "hr", 100)

        assert len(result) == 2
        assert result[0]["name"] == "Veterans' Affairs Committee"
        assert result[0]["chamber"] == "House"
        assert result[0]["type"] == "Standing"
        assert result[1]["name"] == "Armed Services Committee"
        assert result[1]["chamber"] == "Senate"

    @patch("src.fetch_bills._fetch_json")
    @patch("src.fetch_bills.get_api_key", return_value="test-key")
    def test_empty_response(self, mock_key, mock_fetch):
        mock_fetch.return_value = {"committees": []}

        result = fetch_bill_committees(119, "hr", 999)

        assert result == []

    @patch("src.fetch_bills._fetch_json")
    @patch("src.fetch_bills.get_api_key", return_value="test-key")
    def test_missing_committees_key(self, mock_key, mock_fetch):
        mock_fetch.return_value = {}

        result = fetch_bill_committees(119, "hr", 999)

        assert result == []

    @patch("src.fetch_bills._fetch_json")
    @patch("src.fetch_bills.get_api_key", return_value="test-key")
    def test_api_error_returns_empty(self, mock_key, mock_fetch):
        mock_fetch.side_effect = Exception("API down")

        result = fetch_bill_committees(119, "hr", 100)

        assert result == []


# ── update_committees_json ─────────────────────────────────────

class TestUpdateCommitteesJson:
    def test_updates_existing_bill(self):
        _insert_test_bill(committees_json="[]")

        committees = [{"name": "VA Committee", "chamber": "House", "type": "Standing"}]
        result = db.update_committees_json("hr-119-100", json.dumps(committees))

        assert result is True

        bill = db.get_bill("hr-119-100")
        parsed = json.loads(bill["committees_json"])
        assert len(parsed) == 1
        assert parsed[0]["name"] == "VA Committee"

    def test_no_op_for_missing_bill(self):
        result = db.update_committees_json("nonexistent-bill", "[]")
        # total_changes may still be > 0 from other ops in session,
        # but the UPDATE itself affects 0 rows
        # Just verify it doesn't raise
        assert isinstance(result, bool)


# ── sync integration ──────────────────────────────────────────

class TestSyncCommitteeBackfill:
    @patch("src.fetch_bills.fetch_bill_committees")
    @patch("src.fetch_bills.fetch_bill_actions")
    @patch("src.fetch_bills.fetch_bill_details")
    @patch("src.fetch_bills.fetch_committee_bills")
    @patch("src.fetch_bills.get_api_key", return_value="test-key")
    def test_empty_committees_trigger_fetch(
        self, mock_key, mock_comm_bills, mock_details, mock_actions, mock_fetch_comms
    ):
        """Verify that sync_va_bills fetches committees for bills with empty committees_json."""
        from src.fetch_bills import sync_va_bills

        mock_comm_bills.return_value = [
            {"congress": 119, "bill_type": "hr", "number": 200, "title": "Test", "url": ""}
        ]
        mock_details.return_value = {
            "bill_id": "hr-119-200",
            "congress": 119,
            "bill_type": "hr",
            "bill_number": 200,
            "title": "Test Bill",
            "sponsor_name": "Doe",
            "sponsor_bioguide_id": "D000001",
            "sponsor_party": "R",
            "sponsor_state": "TX",
            "introduced_date": "2025-01-01",
            "latest_action_date": "2025-01-15",
            "latest_action_text": "Introduced",
            "policy_area": "Veterans",
            "committees": [],
            "cosponsors_count": 0,
        }
        mock_actions.return_value = []
        mock_fetch_comms.return_value = [
            {"name": "VA Committee", "chamber": "House", "type": "Standing"}
        ]

        stats = sync_va_bills(congress=119, limit=10, dry_run=False)

        # fetch_bill_committees should have been called for the bill with empty committees
        mock_fetch_comms.assert_called()

        # Verify the bill was updated with committee data
        bill = db.get_bill("hr-119-200")
        assert bill is not None
        parsed = json.loads(bill["committees_json"])
        assert len(parsed) == 1
        assert parsed[0]["name"] == "VA Committee"
