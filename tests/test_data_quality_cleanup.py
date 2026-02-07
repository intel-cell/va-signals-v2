"""Tests for data quality cleanup validations.

Covers:
- audit.py: _is_contaminated rejects testclient / injection patterns
- hearings.py: upsert_hearing rejects far-future dates
- helpers.py: insert_source_run rejects stub values
- hearings duplicate event_id handling (issue #13)
"""

from src.auth.audit import _is_contaminated
from src.db import connect, execute
from src.db.hearings import upsert_hearing
from src.db.helpers import insert_source_run

# ---------- audit.py validation ----------


class TestAuditContamination:
    def test_rejects_testclient_ip(self):
        entry = {"ip_address": "testclient", "request_body": "", "user_agent": ""}
        assert _is_contaminated(entry) is True

    def test_rejects_script_injection(self):
        entry = {
            "ip_address": "1.2.3.4",
            "request_body": "<script>alert(1)</script>",
            "user_agent": "",
        }
        assert _is_contaminated(entry) is True

    def test_rejects_drop_table(self):
        entry = {"ip_address": "1.2.3.4", "request_body": "", "user_agent": "DROP TABLE users"}
        assert _is_contaminated(entry) is True

    def test_rejects_drop_table_case_insensitive(self):
        entry = {"ip_address": "1.2.3.4", "request_body": "drop table foo", "user_agent": ""}
        assert _is_contaminated(entry) is True

    def test_allows_normal_entry(self):
        entry = {
            "ip_address": "192.168.1.1",
            "request_body": '{"key": "value"}',
            "user_agent": "Mozilla/5.0",
        }
        assert _is_contaminated(entry) is False

    def test_allows_none_values(self):
        entry = {"ip_address": None, "request_body": None, "user_agent": None}
        assert _is_contaminated(entry) is False


# ---------- hearings.py date validation ----------


class TestHearingsDateValidation:
    def _make_hearing(self, event_id="H-001", hearing_date="2025-03-15"):
        return {
            "event_id": event_id,
            "congress": "119",
            "chamber": "Senate",
            "committee_code": "SSVA",
            "committee_name": "Senate Veterans Affairs",
            "hearing_date": hearing_date,
            "hearing_time": "10:00",
            "title": "Test Hearing",
            "meeting_type": "hearing",
            "status": "scheduled",
            "location": "Room 418",
            "url": "https://example.com",
            "witnesses_json": None,
        }

    def test_rejects_far_future_date(self):
        hearing = self._make_hearing(hearing_date="2099-01-01")
        is_new, changes = upsert_hearing(hearing)
        assert is_new is False
        assert changes == []

        # Verify nothing was inserted
        con = connect()
        cur = execute(con, "SELECT COUNT(*) FROM hearings WHERE event_id = 'H-001'")
        assert cur.fetchone()[0] == 0
        con.close()

    def test_accepts_valid_date(self):
        hearing = self._make_hearing(hearing_date="2025-06-15")
        is_new, changes = upsert_hearing(hearing)
        assert is_new is True

    def test_rejects_year_2100(self):
        hearing = self._make_hearing(event_id="H-002", hearing_date="2100-12-31")
        is_new, changes = upsert_hearing(hearing)
        assert is_new is False
        assert changes == []


# ---------- helpers.py validation ----------


class TestSourceRunValidation:
    def _make_run(self, source_id="fr_delta", started_at="2025-01-15T10:00:00Z"):
        return {
            "source_id": source_id,
            "started_at": started_at,
            "ended_at": "2025-01-15T10:05:00Z",
            "status": "SUCCESS",
            "records_fetched": 5,
            "errors": [],
        }

    def test_rejects_single_char_source_id(self):
        run = self._make_run(source_id="x")
        insert_source_run(run)

        con = connect()
        cur = execute(con, "SELECT COUNT(*) FROM source_runs WHERE source_id = 'x'")
        assert cur.fetchone()[0] == 0
        con.close()

    def test_rejects_empty_source_id(self):
        run = self._make_run(source_id="")
        insert_source_run(run)

        con = connect()
        cur = execute(con, "SELECT COUNT(*) FROM source_runs")
        assert cur.fetchone()[0] == 0
        con.close()

    def test_rejects_single_char_started_at(self):
        run = self._make_run(started_at="x")
        insert_source_run(run)

        con = connect()
        cur = execute(con, "SELECT COUNT(*) FROM source_runs")
        assert cur.fetchone()[0] == 0
        con.close()

    def test_accepts_valid_run(self):
        run = self._make_run()
        insert_source_run(run)

        con = connect()
        cur = execute(con, "SELECT COUNT(*) FROM source_runs WHERE source_id = 'fr_delta'")
        assert cur.fetchone()[0] == 1
        con.close()


# ---------- hearings duplicate event_id (issue #13) ----------


class TestHearingsDuplicateEventId:
    def _make_hearing(self, event_id="H-DUP-001", **overrides):
        base = {
            "event_id": event_id,
            "congress": "119",
            "chamber": "Senate",
            "committee_code": "SSVA",
            "committee_name": "Senate Veterans Affairs",
            "hearing_date": "2025-06-15",
            "hearing_time": "10:00",
            "title": "Original Title",
            "meeting_type": "hearing",
            "status": "scheduled",
            "location": "Room 418",
            "url": "https://example.com",
            "witnesses_json": None,
        }
        base.update(overrides)
        return base

    def test_upsert_same_event_id_updates_not_duplicates(self):
        hearing1 = self._make_hearing(title="Original Title", status="scheduled")
        is_new, changes = upsert_hearing(hearing1)
        assert is_new is True
        assert changes == []

        # Second upsert with same event_id but different status
        hearing2 = self._make_hearing(title="Original Title", status="postponed")
        is_new2, changes2 = upsert_hearing(hearing2)
        assert is_new2 is False
        assert len(changes2) == 1
        assert changes2[0]["field_changed"] == "status"
        assert changes2[0]["old_value"] == "scheduled"
        assert changes2[0]["new_value"] == "postponed"

        # Verify only one row exists
        con = connect()
        cur = execute(con, "SELECT COUNT(*) FROM hearings WHERE event_id = 'H-DUP-001'")
        assert cur.fetchone()[0] == 1

        # Verify status was updated
        cur = execute(con, "SELECT status FROM hearings WHERE event_id = 'H-DUP-001'")
        assert cur.fetchone()[0] == "postponed"
        con.close()
