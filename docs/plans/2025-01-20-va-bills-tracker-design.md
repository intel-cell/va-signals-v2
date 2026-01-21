# VA Bills Tracker - Design Document

## Overview

Track VA-related bills from Congress.gov API. Detect new introductions and status changes, alert via Slack, display in dashboard.

## Data Sources

- **Congress.gov API** - `/committee/{chamber}/{code}/bills` and `/bill/{congress}/{type}/{number}`
- **VA Committees**: `hsvr00` (House), `ssva00` (Senate)
- **API Key**: Existing `congress-api` in macOS Keychain

## Schema

```sql
-- Bills we're tracking
CREATE TABLE IF NOT EXISTS bills (
  bill_id TEXT PRIMARY KEY,
  congress INTEGER NOT NULL,
  bill_type TEXT NOT NULL,
  bill_number INTEGER NOT NULL,
  title TEXT NOT NULL,
  sponsor_name TEXT,
  sponsor_bioguide_id TEXT,
  sponsor_party TEXT,
  sponsor_state TEXT,
  introduced_date TEXT,
  latest_action_date TEXT,
  latest_action_text TEXT,
  policy_area TEXT,
  committees_json TEXT,
  cosponsors_count INTEGER DEFAULT 0,
  first_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Track status changes for alerting
CREATE TABLE IF NOT EXISTS bill_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bill_id TEXT NOT NULL,
  action_date TEXT NOT NULL,
  action_text TEXT NOT NULL,
  action_type TEXT,
  first_seen_at TEXT NOT NULL,
  FOREIGN KEY (bill_id) REFERENCES bills(bill_id),
  UNIQUE(bill_id, action_date, action_text)
);
```

## Modules

### `src/fetch_bills.py`

```python
def get_api_key() -> str
def fetch_committee_bills(committee_code: str, limit: int = 250) -> list[dict]
def fetch_bill_details(congress: int, bill_type: str, number: int) -> dict
def fetch_bill_actions(congress: int, bill_type: str, number: int) -> list[dict]
def sync_va_bills() -> dict  # Returns {new_bills, updated_bills, new_actions}
```

### `src/run_bills.py`

```
Usage:
    python -m src.run_bills [--full] [--summary]
```

- Default: Delta sync
- `--full`: Fetch all bills (initial seed)
- `--summary`: Show stats only

### `src/notify_slack.py` additions

```python
def format_new_bills_alert(bills: list[dict]) -> dict | None
def format_bill_status_alert(actions: list[dict]) -> dict | None
```

### `src/dashboard_api.py` additions

```python
GET /api/bills - List tracked VA bills
GET /api/bills/{bill_id} - Bill details with actions
GET /api/bills/stats - Summary stats
```

### Dashboard UI

- Health card: "Active Bills" count
- New collapsible "VA Legislation" section
- Table: Bill ID, Title, Sponsor, Latest Action, Updated
- Click row to see action history

## Alert Triggers

| Event | Slack Message |
|-------|---------------|
| New bill introduced | "VA Signals — N new bill(s) introduced" |
| Bill status change | "VA Signals — Bill status change: HR 1234 passed committee" |

## Polling Strategy

- Daily sync (or 2x daily)
- Compare `latest_action_date` to detect changes
- ~10-20 API calls per run (well under 5,000/hour limit)

## Files to Create/Modify

| File | Action |
|------|--------|
| `schema.sql` | Add bills, bill_actions tables |
| `src/fetch_bills.py` | New - API fetch logic |
| `src/run_bills.py` | New - CLI runner |
| `src/db.py` | Add bill DB helpers |
| `src/notify_slack.py` | Add bill alert formatters |
| `src/dashboard_api.py` | Add bill endpoints |
| `src/dashboard/static/index.html` | Add legislation section |
| `src/dashboard/static/app.js` | Add bill rendering |
| `src/dashboard/static/style.css` | Add bill styles |
| `Makefile` | Add `bills` target |
