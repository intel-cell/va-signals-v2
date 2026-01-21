# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VA Signals is a fail-closed monitoring system for Veterans Affairs-relevant signals. It tracks Federal Register publications, eCFR regulations, Congressional bills, and committee member rhetoric patterns. The system alerts via Slack only when decision-relevant changes occur.

## Commands

```bash
make init              # Create venv and install dependencies
make test              # Run pytest
make db-init           # Initialize SQLite schema
make dashboard         # Run FastAPI dashboard on port 8000

# Data pipelines
make fr-delta          # Federal Register delta detection
make ecfr-delta        # eCFR Title 38 delta detection
make bills             # Sync VA committee bills from Congress.gov
make agenda-drift      # Run agenda drift detection (baselines + deviations)

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
| Agenda Drift | `ad_members`, `ad_utterances`, `ad_embeddings`, `ad_baselines`, `ad_deviation_events` | `run_agenda_drift.py` |

### Run Status Convention

All pipelines record runs in `source_runs` with status:
- `SUCCESS` - New data found and processed
- `NO_DATA` - Source checked, nothing new (silent)
- `ERROR` - Failure occurred (alerts)

## API Keys

Stored in macOS Keychain, not environment variables:
- `claude-api` - Anthropic API key (for summarization, drift explanations)
- `congress-api` - Congress.gov API key (for bills, transcripts)

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
