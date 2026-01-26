# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VA Signals is a fail-closed monitoring system for Veterans Affairs-relevant signals. It tracks Federal Register publications, eCFR regulations, Congressional bills, committee hearings, oversight reports, and member rhetoric patterns. The system alerts via Slack only when decision-relevant changes occur.

## Commands

```bash
make init              # Create venv and install dependencies
make test              # Run pytest
make db-init           # Initialize SQLite schema
make dashboard         # Run FastAPI dashboard on port 8000

# Federal data pipelines
make fr-delta          # Federal Register delta detection
make ecfr-delta        # eCFR Title 38 delta detection
make bills             # Sync VA committee bills from Congress.gov
make hearings          # Sync committee hearings
make agenda-drift      # Run agenda drift detection (baselines + deviations)

# Oversight monitor (multi-agent)
./.venv/bin/python -m src.run_oversight --all           # Run all agents
./.venv/bin/python -m src.run_oversight --agent gao     # Single agent

# State intelligence
make state-monitor          # Run all state sources
make state-monitor-morning  # Morning run type
make state-monitor-dry      # Dry run (no alerts)
make state-digest           # Generate weekly state digest

# Supporting commands
make summarize         # LLM summarization of pending FR docs
make fetch-transcripts # Fetch hearing transcripts
make embed             # Generate embeddings for utterances
make report-daily      # Generate daily email report
make report-weekly     # Generate weekly email report
```

## Architecture

### Data Flow

```
External Sources → Fetch Modules → SQLite (data/signals.db) → Dashboard API
                                          ↓
                              Slack/Email Alerts
```

### Core Modules

| Module | Purpose |
|--------|---------|
| `src/db.py` | All SQLite operations. Single connection pattern. |
| `src/run_*.py` | CLI runners for each pipeline. Log to `source_runs` table. |
| `src/fetch_*.py` | API/web fetch logic. No DB writes directly. |
| `src/notify_slack.py` | Slack alerting via bot token (not webhooks). |
| `src/dashboard_api.py` | FastAPI backend serving `/api/*` endpoints. |

### Data Sources

| Source | Tables | Runner |
|--------|--------|--------|
| Federal Register | `fr_seen`, `fr_summaries` | `run_fr_delta.py` |
| eCFR Title 38 | `ecfr_seen` | `run_ecfr_delta.py` |
| VA Bills | `bills`, `bill_actions` | `run_bills.py` |
| Hearings | `hearings`, `hearing_updates` | `run_hearings.py` |
| Agenda Drift | `ad_members`, `ad_utterances`, `ad_embeddings`, `ad_baselines`, `ad_deviation_events` | `run_agenda_drift.py` |
| Oversight Monitor | `om_events`, `om_related_coverage`, `om_baselines`, `om_rejected` | `run_oversight.py` |
| State Intelligence | `state_signals`, `state_classifications`, `state_runs` | `src/state/runner.py` |

### Oversight Monitor (`src/oversight/`)

Multi-agent system that monitors oversight bodies for VA-relevant events:

| Agent | Source |
|-------|--------|
| `gao` | GAO reports |
| `oig` | VA Office of Inspector General |
| `crs` | Congressional Research Service |
| `congressional_record` | Congressional Record |
| `committee_press` | Committee press releases |
| `news_wire` | News wire services |
| `investigative` | Investigative journalism |
| `trade_press` | Trade publications |
| `cafc` | Court of Appeals for Federal Circuit |

Pipeline: Raw events → Quality gate → Deduplication → Escalation detection → Storage

### Signals Routing (`src/signals/`)

Rule-based routing engine for processing events through indicators and triggers:
- `envelope.py` - Standardized event wrapper
- `schema/` - YAML-based signal category definitions
- `engine/` - Expression parser and evaluator
- `evaluators/` - Field matchers, text patterns, comparisons
- `adapters/` - Convert source events (hearings, bills) to envelopes
- `suppression.py` - Cooldown-based deduplication

### State Intelligence (`src/state/`)

Monitors state-level VA news and official sources:
- `sources/` - State-specific scrapers (TX, FL, CA) + NewsAPI + RSS
- `classify.py` - Keyword + LLM severity classification
- `runner.py` - Orchestrates morning/evening runs

### Run Status Convention

All pipelines record runs in `source_runs` with status:
- `SUCCESS` - New data found and processed
- `NO_DATA` - Source checked, nothing new (silent)
- `ERROR` - Failure occurred (alerts)

## API Keys

Env vars first (Cloud Run/CI); Keychain fallback for local macOS. Env vars take precedence.
- Env: `ANTHROPIC_API_KEY`, `CONGRESS_API_KEY`, `NEWSAPI_KEY`
- Keychain (macOS): `claude-api`, `congress-api`, `newsapi-key`

Slack credentials are env-only for local and cloud runs.

Retrieval pattern (see `src/fetch_transcripts.py`):
```python
security find-generic-password -s "congress-api" -a "$USER" -w
```

## Non-Negotiables

1. **Fail closed**: Missing/unverifiable data → `NO_DATA` or `ERROR`, never fabricated
2. **Provenance-first**: No downstream signals without source tracking
3. **No demo data in runtime paths**: `config/approved_sources.yaml` enforces allowed sources
4. **Slack is selective**: Only `NEW_DOCS` or `ERROR` trigger alerts. Silence = success.

## Testing

```bash
make test                                    # Run all tests
./.venv/bin/python -m pytest tests/test_provenance_gate.py -v   # Single file
./.venv/bin/python -m pytest -k "test_name" -v                  # Single test
```

## Dashboard

Static files in `src/dashboard/static/` (index.html, app.js, style.css). FastAPI serves them and provides `/api/*` endpoints. Run with `make dashboard`, access at `http://localhost:8000`.
