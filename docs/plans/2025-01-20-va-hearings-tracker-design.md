# VA Hearings Tracker - Design Document

## Overview

Track upcoming VA committee hearings from Congress.gov API. Detect new hearings and status changes (cancelled, rescheduled), alert via Slack, display in dashboard.

## Data Sources

- **Congress.gov API** - `/committee-meeting/{congress}/{chamber}`
- **VA Committees**:
  - `hsvr00` (House VA full committee)
  - `hsvr01` - Compensation, Pension and Insurance
  - `hsvr02` - Education, Training and Employment
  - `hsvr03` - Health
  - `hsvr04` - Housing and Memorial Affairs
  - `hsvr08` - Oversight and Investigations
  - `hsvr10` - Economic Opportunity
  - `hsvr11` - Technology Modernization
  - `ssva00` (Senate VA full committee)
- **API Key**: Existing `congress-api` in macOS Keychain

## Schema

```sql
CREATE TABLE IF NOT EXISTS hearings (
  event_id TEXT PRIMARY KEY,
  congress INTEGER NOT NULL,
  chamber TEXT NOT NULL,
  committee_code TEXT NOT NULL,
  committee_name TEXT,
  hearing_date TEXT NOT NULL,
  hearing_time TEXT,
  title TEXT,
  meeting_type TEXT,
  status TEXT NOT NULL,
  location TEXT,
  url TEXT,
  witnesses_json TEXT,
  first_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hearing_updates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  field_changed TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT,
  detected_at TEXT NOT NULL,
  FOREIGN KEY (event_id) REFERENCES hearings(event_id)
);
```

## Modules

### `src/fetch_hearings.py`

```python
def get_api_key() -> str
def fetch_committee_meetings(chamber: str, congress: int = 119) -> list[dict]
def fetch_meeting_details(event_id: str) -> dict | None
def sync_va_hearings(congress: int = 119) -> dict  # Returns {new_hearings, updated_hearings, changes}
```

### `src/run_hearings.py`

```
Usage:
    python -m src.run_hearings [--full] [--summary]
```

- Default: Sync and alert
- `--full`: Full refresh
- `--summary`: Show stats only

### `src/notify_slack.py` additions

```python
def format_new_hearings_alert(hearings: list[dict]) -> dict | None
def format_hearing_changes_alert(changes: list[dict]) -> dict | None
```

### `src/dashboard_api.py` additions

```python
GET /api/hearings - List hearings (upcoming by default)
GET /api/hearings/stats - Summary stats
```

### Dashboard UI

- New "Upcoming Hearings" section
- Cards: Date, Committee, Title, Status badge
- Status colors: Scheduled (green), Cancelled (red), Rescheduled (yellow)
- Links to Congress.gov

## Alert Triggers

| Event | Slack Message |
|-------|---------------|
| New hearing scheduled | "VA Signals — N new hearing(s) scheduled" |
| Hearing cancelled/rescheduled | "VA Signals — Hearing update" |

## Polling Strategy

- Sync 2x daily (hearings posted ~1 week ahead)
- Compare status, date, title to detect changes
- Store changes in hearing_updates table

## Files to Create/Modify

| File | Action |
|------|--------|
| `schema.sql` | Add hearings, hearing_updates tables |
| `src/fetch_hearings.py` | New - API fetch logic |
| `src/run_hearings.py` | New - CLI runner |
| `src/db.py` | Add hearing DB helpers |
| `src/notify_slack.py` | Add hearing alert formatters |
| `src/dashboard_api.py` | Add hearing endpoints |
| `src/dashboard/static/index.html` | Add hearings section |
| `src/dashboard/static/app.js` | Add hearing rendering |
| `src/dashboard/static/style.css` | Add hearing styles |
| `Makefile` | Add `hearings` target |
