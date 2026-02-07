"""Tests for db.py CRUD functions — covers FR, eCFR, Agenda Drift, Bills,
Hearings, Authority Docs, and LDA helpers."""

import json

import pytest

import src.db as db


# ── helpers ──────────────────────────────────────────────────────

def _make_bill(**overrides):
    base = {
        "bill_id": "hr-118-100",
        "congress": 118,
        "bill_type": "hr",
        "bill_number": 100,
        "title": "Test Bill",
        "sponsor_name": "Smith",
        "sponsor_bioguide_id": "S000001",
        "sponsor_party": "D",
        "sponsor_state": "CA",
        "introduced_date": "2024-01-10",
        "latest_action_date": "2024-02-15",
        "latest_action_text": "Introduced",
        "policy_area": "Veterans",
        "committees_json": "[]",
        "cosponsors_count": 5,
    }
    base.update(overrides)
    return base


def _make_hearing(**overrides):
    base = {
        "event_id": "EVT-001",
        "congress": 119,
        "chamber": "House",
        "committee_code": "hsvr00",
        "committee_name": "Veterans Affairs",
        "hearing_date": "2026-03-01",
        "hearing_time": "10:00",
        "title": "VA Oversight Hearing",
        "meeting_type": "hearing",
        "status": "scheduled",
        "location": "Room 334",
        "url": "https://congress.gov/hearing/1",
        "witnesses_json": "[]",
    }
    base.update(overrides)
    return base


def _make_authority_doc(**overrides):
    base = {
        "doc_id": "auth-001",
        "authority_source": "cfr",
        "authority_type": "regulation",
        "title": "38 CFR Part 3",
        "published_at": "2024-06-01",
        "source_url": "https://ecfr.gov/x",
        "body_text": "Section text",
        "content_hash": "abc123",
        "metadata_json": "{}",
    }
    base.update(overrides)
    return base


# ── FR helpers ───────────────────────────────────────────────────

class TestUpsertFrSeen:
    def test_insert_new_returns_true(self):
        result = db.upsert_fr_seen(
            doc_id="FR-001",
            published_date="2024-01-01",
            first_seen_at="2024-01-02T00:00:00Z",
            source_url="https://fr.gov/1",
        )
        assert result is True

    def test_existing_returns_false(self):
        db.upsert_fr_seen("FR-001", "2024-01-01", "2024-01-02T00:00:00Z", "https://fr.gov/1")
        result = db.upsert_fr_seen("FR-001", "2024-01-01", "2024-01-03T00:00:00Z", "https://fr.gov/1")
        assert result is False

    def test_optional_fields_stored(self):
        db.upsert_fr_seen(
            doc_id="FR-002",
            published_date="2024-01-01",
            first_seen_at="2024-01-02T00:00:00Z",
            source_url="https://fr.gov/2",
            comments_close_date="2024-03-01",
            effective_date="2024-04-01",
            document_type="proposed rule",
            title="Test Rule",
        )
        con = db.connect()
        cur = db.execute(con, "SELECT comments_close_date, effective_date, document_type, title FROM fr_seen WHERE doc_id = 'FR-002'")
        row = cur.fetchone()
        con.close()
        assert row == ("2024-03-01", "2024-04-01", "proposed rule", "Test Rule")


class TestUpdateFrSeenDates:
    def test_update_existing_returns_true(self):
        db.upsert_fr_seen("FR-010", "2024-01-01", "2024-01-02T00:00:00Z", "https://fr.gov/10")
        result = db.update_fr_seen_dates("FR-010", comments_close_date="2024-05-01")
        assert result is True

    def test_update_nonexistent_returns_false(self):
        result = db.update_fr_seen_dates("NOPE", title="whatever")
        assert result is False

    def test_only_updates_provided_fields(self):
        db.upsert_fr_seen(
            "FR-011", "2024-01-01", "2024-01-02T00:00:00Z", "https://fr.gov/11",
            comments_close_date="2024-02-01",
        )
        db.update_fr_seen_dates("FR-011", title="New Title")
        con = db.connect()
        cur = db.execute(con, "SELECT comments_close_date, title FROM fr_seen WHERE doc_id = 'FR-011'")
        row = cur.fetchone()
        con.close()
        assert row == ("2024-02-01", "New Title")

    def test_no_fields_skips_update(self):
        db.upsert_fr_seen("FR-012", "2024-01-01", "2024-01-02T00:00:00Z", "https://fr.gov/12")
        result = db.update_fr_seen_dates("FR-012")
        assert result is True  # exists, but no update needed


class TestGetExistingFrDocIds:
    def test_empty_list_returns_empty(self):
        assert db.get_existing_fr_doc_ids([]) == set()

    def test_returns_existing_subset(self):
        db.upsert_fr_seen("FR-A", "2024-01-01", "2024-01-01T00:00:00Z", "https://fr.gov/a")
        db.upsert_fr_seen("FR-B", "2024-01-01", "2024-01-01T00:00:00Z", "https://fr.gov/b")
        result = db.get_existing_fr_doc_ids(["FR-A", "FR-B", "FR-C"])
        assert result == {"FR-A", "FR-B"}


class TestBulkInsertFrSeen:
    def test_empty_list_returns_zero(self):
        assert db.bulk_insert_fr_seen([]) == 0

    def test_inserts_multiple(self):
        docs = [
            {"doc_id": "BULK-1", "published_date": "2024-01-01", "first_seen_at": "2024-01-01T00:00:00Z", "source_url": "u1"},
            {"doc_id": "BULK-2", "published_date": "2024-01-01", "first_seen_at": "2024-01-01T00:00:00Z", "source_url": "u2"},
        ]
        count = db.bulk_insert_fr_seen(docs)
        assert count == 2

    def test_conflict_skips_existing(self):
        db.upsert_fr_seen("BULK-3", "2024-01-01", "2024-01-01T00:00:00Z", "u3")
        docs = [
            {"doc_id": "BULK-3", "published_date": "2024-01-01", "first_seen_at": "2024-01-01T00:00:00Z", "source_url": "u3"},
            {"doc_id": "BULK-4", "published_date": "2024-01-01", "first_seen_at": "2024-01-01T00:00:00Z", "source_url": "u4"},
        ]
        count = db.bulk_insert_fr_seen(docs)
        assert count == 1


# ── eCFR helpers ─────────────────────────────────────────────────

class TestUpsertEcfrSeen:
    def test_insert_new_returns_true(self):
        result = db.upsert_ecfr_seen("CFR-001", "2024-01-01", "etag1", "2024-01-02T00:00:00Z", "https://ecfr.gov/1")
        assert result is True

    def test_unchanged_returns_false(self):
        db.upsert_ecfr_seen("CFR-002", "2024-01-01", "etag2", "2024-01-02T00:00:00Z", "https://ecfr.gov/2")
        result = db.upsert_ecfr_seen("CFR-002", "2024-01-01", "etag2", "2024-01-03T00:00:00Z", "https://ecfr.gov/2")
        assert result is False

    def test_changed_etag_returns_true(self):
        db.upsert_ecfr_seen("CFR-003", "2024-01-01", "etag3", "2024-01-02T00:00:00Z", "https://ecfr.gov/3")
        result = db.upsert_ecfr_seen("CFR-003", "2024-01-01", "etag3-changed", "2024-01-03T00:00:00Z", "https://ecfr.gov/3")
        assert result is True

    def test_changed_last_modified_returns_true(self):
        db.upsert_ecfr_seen("CFR-004", "2024-01-01", "etag4", "2024-01-02T00:00:00Z", "https://ecfr.gov/4")
        result = db.upsert_ecfr_seen("CFR-004", "2024-02-01", "etag4", "2024-01-03T00:00:00Z", "https://ecfr.gov/4")
        assert result is True


# ── Agenda Drift helpers ─────────────────────────────────────────

class TestAdMember:
    def test_insert_new_returns_true(self):
        assert db.upsert_ad_member("M001", "Sen. Test", party="D", committee="SVAC") is True

    def test_existing_returns_false(self):
        db.upsert_ad_member("M002", "Rep. Existing")
        assert db.upsert_ad_member("M002", "Rep. Existing") is False


class TestAdUtterances:
    def test_bulk_insert_empty(self):
        assert db.bulk_insert_ad_utterances([]) == 0

    def test_bulk_insert_and_get(self):
        db.upsert_ad_member("M010", "Sen. Speaker")
        utts = [
            {"utterance_id": "U001", "member_id": "M010", "hearing_id": "H001", "chunk_ix": 0, "content": "Test speech about veterans.", "spoken_at": "2024-01-15T10:00:00Z"},
            {"utterance_id": "U002", "member_id": "M010", "hearing_id": "H001", "chunk_ix": 1, "content": "Continued remarks.", "spoken_at": "2024-01-15T10:01:00Z"},
        ]
        count = db.bulk_insert_ad_utterances(utts)
        assert count == 2

        fetched = db.get_ad_utterances_for_member("M010")
        assert len(fetched) == 2
        assert fetched[0]["utterance_id"] == "U002"  # ordered DESC

    def test_conflict_skips(self):
        db.upsert_ad_member("M011", "Rep. Dup")
        utts = [{"utterance_id": "U010", "member_id": "M011", "hearing_id": "H002", "chunk_ix": 0, "content": "Original.", "spoken_at": "2024-01-15T10:00:00Z"}]
        db.bulk_insert_ad_utterances(utts)
        count = db.bulk_insert_ad_utterances(utts)
        assert count == 0

    def test_get_ad_utterance_by_id_found(self):
        db.upsert_ad_member("M012", "Sen. Found")
        db.bulk_insert_ad_utterances([
            {"utterance_id": "U020", "member_id": "M012", "hearing_id": "H010", "chunk_ix": 0, "content": "Content here.", "spoken_at": "2024-02-01T09:00:00Z"},
        ])
        result = db.get_ad_utterance_by_id("U020")
        assert result is not None
        assert result["member_name"] == "Sen. Found"

    def test_get_ad_utterance_by_id_not_found(self):
        assert db.get_ad_utterance_by_id("NOPE") is None


class TestAdEmbedding:
    def test_insert_new_returns_true(self):
        db.upsert_ad_member("M020", "Sen. Vec")
        db.bulk_insert_ad_utterances([
            {"utterance_id": "U030", "member_id": "M020", "hearing_id": "H020", "chunk_ix": 0, "content": "x" * 200, "spoken_at": "2024-01-15T10:00:00Z"},
        ])
        assert db.upsert_ad_embedding("U030", [0.1, 0.2, 0.3], "model-v1") is True

    def test_update_existing_returns_false(self):
        db.upsert_ad_member("M021", "Rep. VecUp")
        db.bulk_insert_ad_utterances([
            {"utterance_id": "U031", "member_id": "M021", "hearing_id": "H021", "chunk_ix": 0, "content": "y" * 200, "spoken_at": "2024-01-15T10:00:00Z"},
        ])
        db.upsert_ad_embedding("U031", [0.1, 0.2], "model-v1")
        assert db.upsert_ad_embedding("U031", [0.3, 0.4], "model-v2") is False

    def test_get_embeddings_for_member(self):
        db.upsert_ad_member("M022", "Sen. Emb")
        db.bulk_insert_ad_utterances([
            {"utterance_id": "U032", "member_id": "M022", "hearing_id": "H022", "chunk_ix": 0, "content": "a" * 200, "spoken_at": "2024-01-15T10:00:00Z"},
        ])
        db.upsert_ad_embedding("U032", [0.5, 0.6], "model-v1")
        results = db.get_ad_embeddings_for_member("M022", min_content_length=100)
        assert len(results) == 1
        assert results[0][1] == [0.5, 0.6]

    def test_get_embeddings_filters_short_content(self):
        db.upsert_ad_member("M023", "Rep. Short")
        db.bulk_insert_ad_utterances([
            {"utterance_id": "U033", "member_id": "M023", "hearing_id": "H023", "chunk_ix": 0, "content": "short", "spoken_at": "2024-01-15T10:00:00Z"},
        ])
        db.upsert_ad_embedding("U033", [0.1], "model-v1")
        results = db.get_ad_embeddings_for_member("M023", min_content_length=100)
        assert len(results) == 0


class TestAdBaseline:
    def test_insert_and_get(self):
        db.upsert_ad_member("M030", "Sen. Base")
        baseline_id = db.insert_ad_baseline("M030", [0.1, 0.2], mu=0.5, sigma=0.1, n=50)
        assert isinstance(baseline_id, int)

        result = db.get_latest_ad_baseline("M030")
        assert result is not None
        assert result["mu"] == 0.5
        assert result["sigma"] == 0.1
        assert result["n"] == 50
        assert result["vec_mean"] == [0.1, 0.2]

    def test_get_latest_returns_most_recent(self):
        db.upsert_ad_member("M031", "Rep. Latest")
        db.insert_ad_baseline("M031", [0.1], mu=0.3, sigma=0.1, n=10)
        db.insert_ad_baseline("M031", [0.2], mu=0.6, sigma=0.2, n=20)
        result = db.get_latest_ad_baseline("M031")
        assert result["n"] == 20

    def test_get_no_baseline_returns_none(self):
        assert db.get_latest_ad_baseline("NOBODY") is None


class TestAdDeviationEvents:
    def _setup_member_baseline(self):
        db.upsert_ad_member("M040", "Sen. Dev")
        db.bulk_insert_ad_utterances([
            {"utterance_id": "U040", "member_id": "M040", "hearing_id": "H040", "chunk_ix": 0, "content": "Test content.", "spoken_at": "2024-01-15T10:00:00Z"},
        ])
        baseline_id = db.insert_ad_baseline("M040", [0.1], mu=0.5, sigma=0.1, n=50)
        return baseline_id

    def test_insert_and_query(self):
        bl_id = self._setup_member_baseline()
        event = {
            "member_id": "M040",
            "hearing_id": "H040",
            "utterance_id": "U040",
            "baseline_id": bl_id,
            "cos_dist": 0.85,
            "zscore": 3.5,
            "detected_at": "2024-02-01T12:00:00Z",
            "note": None,
        }
        event_id = db.insert_ad_deviation_event(event)
        assert isinstance(event_id, int)

        events = db.get_ad_deviation_events(limit=10, min_zscore=3.0)
        assert len(events) == 1
        assert events[0]["zscore"] == 3.5
        assert events[0]["member_name"] == "Sen. Dev"

    def test_member_deviation_history(self):
        bl_id = self._setup_member_baseline()
        db.insert_ad_deviation_event({
            "member_id": "M040", "hearing_id": "H040", "utterance_id": "U040",
            "baseline_id": bl_id, "cos_dist": 0.8, "zscore": 3.0,
        })
        history = db.get_ad_member_deviation_history("M040")
        assert len(history) == 1

    def test_recent_deviations_for_hearing(self):
        bl_id = self._setup_member_baseline()
        db.insert_ad_deviation_event({
            "member_id": "M040", "hearing_id": "H040", "utterance_id": "U040",
            "baseline_id": bl_id, "cos_dist": 0.7, "zscore": 2.5,
        })
        results = db.get_ad_recent_deviations_for_hearing("M040", "H040")
        assert len(results) == 1
        assert results[0]["zscore"] == 2.5

    def test_update_deviation_note(self):
        bl_id = self._setup_member_baseline()
        eid = db.insert_ad_deviation_event({
            "member_id": "M040", "hearing_id": "H040", "utterance_id": "U040",
            "baseline_id": bl_id, "cos_dist": 0.9, "zscore": 4.0,
        })
        db.update_ad_deviation_note(eid, "Explained by topic shift")
        events = db.get_ad_deviation_events(limit=10)
        found = [e for e in events if e["id"] == eid]
        assert found[0]["note"] == "Explained by topic shift"

    def test_get_deviations_without_notes(self):
        bl_id = self._setup_member_baseline()
        db.insert_ad_deviation_event({
            "member_id": "M040", "hearing_id": "H040", "utterance_id": "U040",
            "baseline_id": bl_id, "cos_dist": 0.6, "zscore": 2.0,
        })
        results = db.get_ad_deviations_without_notes()
        assert len(results) >= 1


class TestAdTypicalUtterances:
    def test_returns_non_deviation_utterances(self):
        db.upsert_ad_member("M050", "Sen. Typical")
        db.bulk_insert_ad_utterances([
            {"utterance_id": "U050", "member_id": "M050", "hearing_id": "H050", "chunk_ix": 0, "content": "Normal speech.", "spoken_at": "2024-01-15T10:00:00Z"},
        ])
        db.upsert_ad_embedding("U050", [0.1], "model-v1")
        results = db.get_ad_typical_utterances("M050")
        assert len(results) == 1

    def test_exclude_utterance_id(self):
        db.upsert_ad_member("M051", "Rep. Excl")
        db.bulk_insert_ad_utterances([
            {"utterance_id": "U051", "member_id": "M051", "hearing_id": "H051", "chunk_ix": 0, "content": "Speech A.", "spoken_at": "2024-01-15T10:00:00Z"},
            {"utterance_id": "U052", "member_id": "M051", "hearing_id": "H051", "chunk_ix": 1, "content": "Speech B.", "spoken_at": "2024-01-15T10:01:00Z"},
        ])
        db.upsert_ad_embedding("U051", [0.1], "model-v1")
        db.upsert_ad_embedding("U052", [0.2], "model-v1")
        results = db.get_ad_typical_utterances("M051", exclude_utterance_id="U051")
        ids = [r["utterance_id"] for r in results]
        assert "U051" not in ids


# ── Bills helpers ────────────────────────────────────────────────

class TestBillsCRUD:
    def test_upsert_new_bill(self):
        assert db.upsert_bill(_make_bill()) is True

    def test_upsert_existing_bill_updates(self):
        db.upsert_bill(_make_bill())
        assert db.upsert_bill(_make_bill(title="Updated Title")) is False

    def test_get_bill_found(self):
        db.upsert_bill(_make_bill())
        bill = db.get_bill("hr-118-100")
        assert bill is not None
        assert bill["title"] == "Test Bill"
        assert bill["sponsor_party"] == "D"

    def test_get_bill_not_found(self):
        assert db.get_bill("nope") is None

    def test_get_bills_all(self):
        db.upsert_bill(_make_bill(bill_id="b1", latest_action_date="2024-01-01"))
        db.upsert_bill(_make_bill(bill_id="b2", latest_action_date="2024-02-01"))
        bills = db.get_bills(limit=10)
        assert len(bills) == 2
        assert bills[0]["bill_id"] == "b2"  # ordered by latest_action_date DESC

    def test_get_bills_by_congress(self):
        db.upsert_bill(_make_bill(bill_id="b3", congress=118))
        db.upsert_bill(_make_bill(bill_id="b4", congress=119))
        bills = db.get_bills(congress=118)
        assert all(b["congress"] == 118 for b in bills)

    def test_get_new_bills_since(self):
        db.upsert_bill(_make_bill(bill_id="bs1"))
        bills = db.get_new_bills_since("2000-01-01T00:00:00Z")
        assert len(bills) >= 1

    def test_get_new_bills_since_none(self):
        bills = db.get_new_bills_since("2099-01-01T00:00:00Z")
        assert bills == []


class TestBillActions:
    def test_insert_new_action(self):
        db.upsert_bill(_make_bill())
        result = db.insert_bill_action("hr-118-100", {
            "action_date": "2024-02-20",
            "action_text": "Referred to committee",
            "action_type": "IntroReferral",
        })
        assert result is True

    def test_duplicate_action_skips(self):
        db.upsert_bill(_make_bill())
        action = {"action_date": "2024-02-20", "action_text": "Referred to committee"}
        db.insert_bill_action("hr-118-100", action)
        result = db.insert_bill_action("hr-118-100", action)
        assert result is False

    def test_get_bill_actions(self):
        db.upsert_bill(_make_bill())
        db.insert_bill_action("hr-118-100", {"action_date": "2024-02-20", "action_text": "Referred"})
        db.insert_bill_action("hr-118-100", {"action_date": "2024-03-01", "action_text": "Passed"})
        actions = db.get_bill_actions("hr-118-100")
        assert len(actions) == 2
        assert actions[0]["action_date"] == "2024-03-01"  # DESC

    def test_get_new_actions_since(self):
        db.upsert_bill(_make_bill())
        db.insert_bill_action("hr-118-100", {"action_date": "2024-02-20", "action_text": "Committee hearing"})
        actions = db.get_new_actions_since("2000-01-01T00:00:00Z")
        assert len(actions) >= 1
        assert actions[0]["bill_title"] == "Test Bill"


class TestBillStats:
    def test_empty_db_stats(self):
        stats = db.get_bill_stats()
        assert stats["total_bills"] == 0
        assert stats["total_actions"] == 0
        assert stats["most_recent"] is None

    def test_populated_stats(self):
        db.upsert_bill(_make_bill(bill_id="s1", sponsor_party="R"))
        db.upsert_bill(_make_bill(bill_id="s2", sponsor_party="D"))
        db.insert_bill_action("s1", {"action_date": "2024-01-01", "action_text": "Introduced"})
        stats = db.get_bill_stats()
        assert stats["total_bills"] == 2
        assert stats["total_actions"] == 1
        assert "R" in stats["by_party"]
        assert stats["most_recent"] is not None


# ── Hearings helpers ─────────────────────────────────────────────

class TestHearingsCRUD:
    def test_upsert_new_hearing(self):
        is_new, changes = db.upsert_hearing(_make_hearing())
        assert is_new is True
        assert changes == []

    def test_upsert_no_change(self):
        db.upsert_hearing(_make_hearing())
        is_new, changes = db.upsert_hearing(_make_hearing())
        assert is_new is False
        assert changes == []

    def test_upsert_detects_change(self):
        db.upsert_hearing(_make_hearing())
        is_new, changes = db.upsert_hearing(_make_hearing(status="cancelled"))
        assert is_new is False
        assert len(changes) == 1
        assert changes[0]["field_changed"] == "status"
        assert changes[0]["old_value"] == "scheduled"
        assert changes[0]["new_value"] == "cancelled"

    def test_get_hearing_found(self):
        db.upsert_hearing(_make_hearing())
        h = db.get_hearing("EVT-001")
        assert h is not None
        assert h["title"] == "VA Oversight Hearing"

    def test_get_hearing_not_found(self):
        assert db.get_hearing("NOPE") is None

    def test_get_hearings_upcoming(self):
        db.upsert_hearing(_make_hearing(event_id="EVT-F", hearing_date="2035-01-01"))
        db.upsert_hearing(_make_hearing(event_id="EVT-P", hearing_date="2000-01-01"))
        upcoming = db.get_hearings(upcoming=True, limit=100)
        ids = [h["event_id"] for h in upcoming]
        assert "EVT-F" in ids
        assert "EVT-P" not in ids

    def test_get_hearings_by_committee(self):
        db.upsert_hearing(_make_hearing(event_id="EVT-C1", committee_code="hsvr00"))
        db.upsert_hearing(_make_hearing(event_id="EVT-C2", committee_code="ssva00"))
        results = db.get_hearings(upcoming=False, committee="hsvr00")
        assert all(h["committee_code"] == "hsvr00" for h in results)


class TestHearingUpdates:
    def test_insert_hearing_update(self):
        db.upsert_hearing(_make_hearing())
        uid = db.insert_hearing_update("EVT-001", "status", "scheduled", "cancelled")
        assert isinstance(uid, int)

    def test_get_hearing_updates_by_event(self):
        db.upsert_hearing(_make_hearing())
        db.insert_hearing_update("EVT-001", "status", "scheduled", "postponed")
        updates = db.get_hearing_updates(event_id="EVT-001")
        assert len(updates) == 1
        assert updates[0]["field_changed"] == "status"

    def test_get_hearing_updates_all(self):
        db.upsert_hearing(_make_hearing())
        db.insert_hearing_update("EVT-001", "location", "Room 334", "Room 100")
        updates = db.get_hearing_updates()
        assert len(updates) >= 1

    def test_get_new_hearings_since(self):
        db.upsert_hearing(_make_hearing(event_id="EVT-NEW"))
        results = db.get_new_hearings_since("2000-01-01T00:00:00Z")
        assert len(results) >= 1

    def test_get_hearing_changes_since(self):
        db.upsert_hearing(_make_hearing())
        db.upsert_hearing(_make_hearing(status="postponed"))
        changes = db.get_hearing_changes_since("2000-01-01T00:00:00Z")
        assert len(changes) >= 1


class TestHearingStats:
    def test_empty_stats(self):
        stats = db.get_hearing_stats()
        assert stats["total"] == 0
        assert stats["upcoming"] == 0

    def test_populated_stats(self):
        db.upsert_hearing(_make_hearing(event_id="ST-1", hearing_date="2035-06-01"))
        db.upsert_hearing(_make_hearing(event_id="ST-2", hearing_date="2000-01-01"))
        stats = db.get_hearing_stats()
        assert stats["total"] == 2
        assert stats["upcoming"] >= 1


# ── Authority Docs helpers ───────────────────────────────────────

class TestAuthorityDocsCRUD:
    def test_insert_new_returns_true(self):
        assert db.upsert_authority_doc(_make_authority_doc()) is True

    def test_unchanged_returns_false(self):
        db.upsert_authority_doc(_make_authority_doc())
        assert db.upsert_authority_doc(_make_authority_doc()) is False

    def test_changed_hash_updates(self):
        db.upsert_authority_doc(_make_authority_doc())
        result = db.upsert_authority_doc(_make_authority_doc(content_hash="new-hash"))
        assert result is True
        doc = db.get_authority_doc("auth-001")
        assert doc["version"] == 2

    def test_get_authority_doc(self):
        db.upsert_authority_doc(_make_authority_doc())
        doc = db.get_authority_doc("auth-001")
        assert doc is not None
        assert doc["title"] == "38 CFR Part 3"

    def test_get_authority_doc_not_found(self):
        assert db.get_authority_doc("nope") is None

    def test_get_authority_docs_all(self):
        db.upsert_authority_doc(_make_authority_doc(doc_id="a1"))
        db.upsert_authority_doc(_make_authority_doc(doc_id="a2"))
        docs = db.get_authority_docs()
        assert len(docs) == 2

    def test_get_authority_docs_by_source(self):
        db.upsert_authority_doc(_make_authority_doc(doc_id="a3", authority_source="cfr"))
        db.upsert_authority_doc(_make_authority_doc(doc_id="a4", authority_source="fr"))
        docs = db.get_authority_docs(authority_source="cfr")
        assert all(d["authority_source"] == "cfr" for d in docs)

    def test_get_by_hash(self):
        db.upsert_authority_doc(_make_authority_doc())
        doc = db.get_authority_doc_by_hash("abc123")
        assert doc is not None
        assert doc["doc_id"] == "auth-001"

    def test_get_by_hash_not_found(self):
        assert db.get_authority_doc_by_hash("no-hash") is None

    def test_fetch_unrouted(self):
        db.upsert_authority_doc(_make_authority_doc(doc_id="unrouted-1"))
        results = db.fetch_unrouted_authority_docs()
        assert len(results) >= 1

    def test_mark_routed(self):
        db.upsert_authority_doc(_make_authority_doc(doc_id="route-1"))
        db.mark_authority_doc_routed("route-1")
        doc = db.get_authority_doc("route-1")
        assert doc["routed_at"] is not None
        # Should not appear in unrouted anymore
        unrouted = db.fetch_unrouted_authority_docs()
        ids = [d["doc_id"] for d in unrouted]
        assert "route-1" not in ids


# ── LDA helpers ──────────────────────────────────────────────────

class TestLdaCRUD:
    def _make_filing(self, **overrides):
        base = {
            "filing_uuid": "LDA-001",
            "filing_type": "LD-2",
            "filing_year": 2024,
            "filing_period": "Q1",
            "dt_posted": "2024-04-01",
            "registrant_name": "ACME Lobby",
            "registrant_id": "R001",
            "client_name": "Big Corp",
            "client_id": "C001",
            "income_amount": 100000.0,
            "expense_amount": None,
            "lobbying_issues_json": "[]",
            "specific_issues_text": "VA benefits",
            "govt_entities_json": "[]",
            "lobbyists_json": "[]",
            "foreign_entity_listed": 0,
            "foreign_entities_json": None,
            "covered_positions_json": None,
            "source_url": "https://lda.senate.gov/x",
            "first_seen_at": "2024-04-02T00:00:00Z",
            "updated_at": "2024-04-02T00:00:00Z",
            "va_relevance_score": "HIGH",
            "va_relevance_reason": "Direct VA reference",
        }
        base.update(overrides)
        return base

    def test_insert_new_returns_true(self):
        assert db.upsert_lda_filing(self._make_filing()) is True

    def test_existing_returns_false(self):
        db.upsert_lda_filing(self._make_filing())
        assert db.upsert_lda_filing(self._make_filing()) is False

    def test_insert_lda_alert(self):
        db.upsert_lda_filing(self._make_filing())
        alert_id = db.insert_lda_alert({
            "filing_uuid": "LDA-001",
            "alert_type": "foreign_entity",
            "severity": "HIGH",
            "summary": "Foreign entity detected",
            "details_json": "{}",
            "created_at": "2024-04-03T00:00:00Z",
        })
        assert isinstance(alert_id, int)

    def test_get_new_filings_since(self):
        db.upsert_lda_filing(self._make_filing())
        results = db.get_new_lda_filings_since("2000-01-01T00:00:00Z")
        assert len(results) == 1
        assert results[0]["registrant_name"] == "ACME Lobby"

    def test_get_lda_stats(self):
        db.upsert_lda_filing(self._make_filing())
        db.insert_lda_alert({
            "filing_uuid": "LDA-001", "alert_type": "test", "severity": "LOW",
            "summary": "Test", "details_json": "{}", "created_at": "2024-04-03T00:00:00Z",
        })
        stats = db.get_lda_stats()
        assert stats["total_filings"] == 1
        assert stats["unacknowledged_alerts"] == 1


# ── Core helpers ─────────────────────────────────────────────────

class TestCoreHelpers:
    def test_table_exists(self):
        con = db.connect()
        assert db.table_exists(con, "fr_seen") is True
        assert db.table_exists(con, "nonexistent_table") is False
        con.close()

    def test_insert_source_run(self):
        db.insert_source_run({
            "source_id": "test_source",
            "started_at": "2024-01-01T00:00:00Z",
            "ended_at": "2024-01-01T01:00:00Z",
            "status": "SUCCESS",
            "records_fetched": 10,
            "errors": [],
        })
        con = db.connect()
        cur = db.execute(con, "SELECT source_id, status FROM source_runs WHERE source_id = 'test_source'")
        row = cur.fetchone()
        con.close()
        assert row == ("test_source", "SUCCESS")

    def test_insert_returning_id(self):
        con = db.connect()
        rid = db.insert_returning_id(
            con,
            "INSERT INTO source_runs(source_id, started_at, ended_at, status, records_fetched, errors_json) VALUES(:source_id, :started_at, :ended_at, :status, :records_fetched, :errors_json)",
            {"source_id": "x", "started_at": "a", "ended_at": "b", "status": "OK", "records_fetched": 0, "errors_json": "[]"},
        )
        con.commit()
        con.close()
        assert isinstance(rid, int)

    def test_execute_no_params(self):
        con = db.connect()
        cur = db.execute(con, "SELECT COUNT(*) FROM fr_seen")
        assert cur.fetchone()[0] == 0
        con.close()

    def test_executemany_empty(self):
        con = db.connect()
        cur = db.executemany(con, "INSERT INTO fr_seen(doc_id, published_date, first_seen_at, source_url) VALUES(?, ?, ?, ?)", [])
        con.close()

    def test_assert_tables_exist(self):
        db.assert_tables_exist()  # Should not raise
