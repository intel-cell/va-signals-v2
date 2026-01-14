
# VA Signals & Indicators Intelligence System (V2)

Disciplined, fail-closed monitoring of authoritative Veterans Affairs–relevant signals.

**Current capability (Phase 1):** Detect and deduplicate new Federal Register (FR) daily XML releases via GovInfo Bulk Data, persist baselines, and alert only when something changes or breaks.

This repo is a clean-room rebuild. Doctrine and constraints are first-class.

---

## What this system does today

### 1) Daily FR delta detection (authoritative source)
- Pulls from GovInfo FR bulk XML (no API key): `https://www.govinfo.gov/bulkdata/FR/`
- Enumerates recent FR XML files under year/month folders (e.g., `FR-YYYY-MM-DD.xml`)
- Maintains a **baseline** in SQLite (`data/signals.db`) to prevent duplicate alerts
- Produces **run artifacts** and **run logs** for auditability

### 2) Fail-closed behavior
- If the source is unreachable or parsing fails → the run is marked **ERROR** and alerts
- If nothing new is published → the run is **NO_DATA** and remains silent
- No demo/sample/mock data is permitted in runtime paths

---

## Why Slack alerts are the point (and why they are not “annoying pings”)

Slack is not there to tell you “the internet exists.” Slack is there to:

1) **Interrupt leadership only when decision space changes**
   - New FR publication is a legally binding event that can change timelines, compliance posture, and operational risk.

2) **Guarantee you don’t miss it**
   - A phone check is human-dependent and non-auditable. This is continuous, logged, and repeatable.

3) **Provide a permanent, time-stamped audit trail**
   - When leadership asks “When did we know?” you can point to run logs + Slack timestamp.

4) **Fail loudly when reality is unavailable**
   - Silence is success only when the system has verified the world. Errors are not silent.

**Design principle:** Monitor continuously. Interrupt selectively. Speak only when it changes outcomes.

---

## Exactly what Slack messages are sent

Slack sends **only two categories** of messages:

### A) New FR documents detected
Triggered when one or more new FR XML files appear that were not in the baseline.

**Example (includes up to 10 doc IDs + links):**
```
VA Signals — FR Delta NEW DOCS: 2
source=govinfo_fr_bulk records_scanned=46

- FR-2026-01-13.xml — https://www.govinfo.gov/bulkdata/FR/2026/01/FR-2026-01-13.xml
- FR-2026-01-12.xml — https://www.govinfo.gov/bulkdata/FR/2026/01/FR-2026-01-12.xml
```
If more than 10 documents are new, Slack shows the first 10 and appends `(+N more)`.

### B) Ingestion failure / verification failure
Triggered when the system cannot verify the source (network error, parsing error, schema error).

**Example:**
```
VA Signals — FR Delta ERROR
source=govinfo_fr_bulk records=0 errors=['EXCEPTION: TimeoutError(...)']
```

### What Slack does NOT send
- No “still running” messages
- No daily noise
- No “NO_DATA” pings

**Steady state:** Slack is quiet.

---

## How often it pulls, and how

### Scheduling
GitHub Actions runs the pipeline daily at **06:15 ET** (11:15 UTC during EST) via cron, with manual dispatch enabled.

### Execution flow
1. Checkout repo
2. Install dependencies
3. Run tests
4. Initialize DB schema
5. Run FR delta
6. If **NEW DOCS** or **ERROR**, send Slack message

---

## Repository layout

- `config/approved_sources.yaml` — allow-list of sources (fail-closed, no demo)
- `schemas/` — JSON Schemas
  - `source_run.schema.json` — validated run records
  - `signal.schema.json` — downstream signal objects (future)
- `schema.sql` — SQLite schema
- `src/`
  - `fr_bulk.py` — GovInfo FR traversal + package enumeration
  - `run_fr_delta.py` — baseline/delta runner + artifacts + Slack alert decision
  - `fetch_fr_ping.py` — reachability ping (HEAD) + run record artifact
  - `db.py` — SQLite helpers (`source_runs`, `fr_seen`)
  - `provenance.py` — provenance gate for downstream signals
  - `notify_slack.py` — Slack App bot posting (`SLACK_BOT_TOKEN` + `SLACK_CHANNEL`)
- `tests/` — pytest tests (provenance gate + Slack formatting)
- `outputs/runs/` — generated run artifacts (ignored by git)
- `docs/` — governance/doctrine/validation stubs

---

## Setup and commands

### Install
```bash
make init
```

### Tests
```bash
make test
```

### Initialize DB
```bash
make db-init
```

### Run FR delta
```bash
make fr-delta
```

### Optional ping
```bash
make fr-ping
```

---

## Secrets (GitHub Actions)

Set these as **repository secrets**:
- `SLACK_BOT_TOKEN` — Slack App Bot User OAuth Token (`xoxb-...`)
- `SLACK_CHANNEL` — Slack channel ID for `sof-werks` (e.g., `CXXXXXXXX`)

---

## Non-negotiables (binding)

1) **Fail closed**: missing/unverifiable data → **NO DATA** or **ERROR**, never fabricated.
2) **Provenance-first**: no downstream signals without provenance fields.
3) **No demo data in runtime paths**.
4) **Two-gate doctrine** (future signals): Authority validation → Change detection.

---

## AI / Codex Usage

AI tools are allowed to assist implementation only. They are not allowed to invent facts, generate signals, or backfill missing data.

**Important:** This repo does not use Slack incoming webhooks. Alerting is via Slack App bot token + channel ID (`SLACK_BOT_TOKEN`, `SLACK_CHANNEL`).

When using Codex, enforce: **one task = one commit**, and use the work-order template in `docs/governance/AI_USAGE_POLICY.md`.

---

## What’s next (Phase 2)

Next improvements are straightforward:
- Add eCFR (Title 38) integration to track incorporation lag after FR publication
- Add routing/severity (VA relevance filters, rule types)

This system is infrastructure. It’s boring on purpose.