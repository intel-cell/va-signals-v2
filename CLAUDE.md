# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VA Signals is a fail-closed monitoring system for Veterans Affairs-relevant signals. It tracks Federal Register publications, eCFR regulations, Congressional bills, committee hearings, oversight reports, member rhetoric patterns, state-level intelligence, authority documents, and battlefield decision gates. The system alerts via email only when decision-relevant changes occur.

**Version**: 2.0.0 | **Python**: >=3.11 | **Database**: SQLite (dev) / PostgreSQL (prod)

## Commands

```bash
make init              # Create venv and install dependencies
make test              # Run pytest (70% coverage minimum enforced)
make db-init           # Initialize SQLite schema
make dashboard         # Run FastAPI dashboard on port 8000

# Federal data pipelines
make fr-delta          # Federal Register delta detection
make ecfr-delta        # eCFR Title 38 delta detection
make bills             # Sync VA committee bills from Congress.gov
make hearings          # Sync committee hearings
make agenda-drift      # Run agenda drift detection (baselines + deviations)

# Oversight monitor (multi-agent)
./.venv/bin/python -m src.run_oversight run             # Run all agents
./.venv/bin/python -m src.run_oversight run --agent gao # Single agent
./.venv/bin/python -m src.run_oversight baseline        # Build 90-day baselines
./.venv/bin/python -m src.run_oversight status          # Show status + baselines

# State intelligence
make state-monitor          # Run all state sources
make state-monitor-morning  # Morning run type
make state-monitor-evening  # Evening run type
make state-monitor-dry      # Dry run (no alerts)
make state-digest           # Generate weekly state digest

# LDA Lobbying Disclosure
make lda-daily         # Daily LDA delta detection (VA-targeting filings)
make lda-summary       # Show LDA filing statistics

# Phase 2 commands
make battlefield       # Run all battlefield gates
make battlefield-init  # Initialize battlefield data
make authority-docs    # Fetch authority documents (OMB, VA pubs, Whitehouse)

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
External Sources --> Fetch Modules --> SQLite/PostgreSQL --> Dashboard API
                                             |                    |
                                       Email Alerts        WebSocket Push
```

### Core Modules

| Module | Purpose |
|--------|---------|
| `src/db.py` | All DB operations. SQLite + PostgreSQL dual support. Backend auto-detected via `DATABASE_URL`. |
| `src/run_*.py` | CLI runners for each pipeline. Log to `source_runs` table. |
| `src/fetch_*.py` | API/web fetch logic. No DB writes directly. |
| `src/notify_email.py` | Email alerting via SMTP (Gmail). |
| `src/dashboard_api.py` | FastAPI backend serving `/api/*` endpoints + static files. |

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
| Authority Docs | via `fr_seen` / dedicated tables | `run_authority_docs.py` |
| Battlefield | via trend/gate tables | `run_battlefield.py` |
| LDA Lobbying Disclosure | `lda_filings`, `lda_alerts` | `run_lda.py` |

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

Pipeline: Raw events -> Quality gate -> Deduplication -> Escalation detection -> Storage

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

### Authentication & Authorization (`src/auth/`)

Firebase-based authentication with role-based access control:
- `api.py` - Login, token verification, session management endpoints
- `firebase_config.py` - Firebase configuration
- `models.py` - User, UserRole, AuthContext data models
- `rbac.py` - RBAC enforcement (roles: commander, leadership, analyst, viewer)
- `middleware.py` - Auth middleware for request pipelines
- `audit.py` - Audit logging for all user actions

### Multi-Tenant Support (`src/tenants/`)

Organization-level data isolation:
- `api.py` - Tenant management endpoints
- `manager.py` - Tenant lifecycle management
- `middleware.py` - Tenant isolation middleware
- `models.py` - Tenant, TenantPlan, TenantStatus models

### CEO Brief (`src/ceo_brief/`)

Executive briefing generation:
- `aggregator.py` - Aggregates top signals for leadership
- `analyst.py` - LLM-based analysis for briefs
- `generator.py` - Generates structured brief documents
- `runner.py` - CLI runner for brief generation
- `api.py` - API endpoints for brief retrieval

### Battlefield / Gate Detection (`src/battlefield/`)

Time-sensitive decision gate tracking:
- `calendar.py` - Gate/event calendar management
- `gate_detection.py` - Critical decision point detection
- `integrations.py` - Integration with oversight/signals
- `models.py` - Gate, Vehicle, Posture models

### Evidence & Arguments (`src/evidence/`)

Objection library and evidence for Congressional arguments:
- `extractors.py` - Extract evidence from raw sources
- `generator.py` - Generate evidence documents
- `validator.py` - Validate evidence quality
- `alpha_integration.py` / `delta_integration.py` - Source integrations

### Trends & Analytics (`src/trends/`)

Historical trend aggregation:
- `aggregator.py` - Daily/weekly statistics
- `queries.py` - SQL queries for trend data
- Tables: `trend_daily_signals`, `trend_daily_source_health`, `trend_weekly_oversight`, `trend_daily_battlefield`

### ML Scoring (`src/ml/`)

Machine learning-based signal scoring:
- `features.py` - Feature engineering for classification
- `scoring.py` - Severity/relevance scoring algorithms
- Requires `sentence-transformers>=2.2.0`

### Resilience (`src/resilience/`)

Fault tolerance patterns for external service calls:
- `circuit_breaker.py` - Circuit breaker pattern
- `rate_limiter.py` - Rate limiting
- `retry.py` - Retry with exponential backoff

### WebSocket (`src/websocket/`)

Real-time signal push:
- `manager.py` - Connection management
- `broadcast.py` - Broadcast mechanism for live updates
- `api.py` - WebSocket route handlers

### Authority Documents

Fetches authoritative source documents:
- `src/fetch_omb_guidance.py` - OMB memoranda and guidance
- `src/fetch_omb_internal_drop.py` - Internal OMB documents
- `src/fetch_reginfo_pra.py` - RegInfo.gov PRA data
- `src/fetch_va_pubs.py` - VA publications
- `src/fetch_whitehouse.py` - Whitehouse directives

### Run Status Convention

All pipelines record runs in `source_runs` with status:
- `SUCCESS` - New data found and processed
- `NO_DATA` - Source checked, nothing new (silent)
- `ERROR` - Failure occurred (alerts)

## Database

### Dual Backend Support

- **SQLite** (default): `data/signals.db` - used for local development
- **PostgreSQL**: Set `DATABASE_URL` env var - used in production (Cloud Run)
- `schema.sql` - SQLite schema
- `schema.postgres.sql` - PostgreSQL schema
- `src/db.py` auto-detects backend and normalizes parameter styles (`:name` vs `%(name)s`)

### Migrations

Located in `migrations/`:
1. `001_add_fr_date_columns.py` - FR date columns
2. `002_add_trend_tables.py` - Trend/analytics tables
3. `003_ensure_all_tables.py` - Audit log table
4. `004_add_multi_tenant_tables.py` - Multi-tenant tables (tenants, tenant_settings, tenant_members)

## API Keys

Env vars first (Cloud Run/CI); Keychain fallback for local macOS. Env vars take precedence.
- Env: `ANTHROPIC_API_KEY`, `CONGRESS_API_KEY`, `NEWSAPI_KEY`
- Keychain (macOS): `claude-api`, `congress-api`, `newsapi-key`

Email credentials are env-only (see `.env.cron`):
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `EMAIL_TO`

Firebase auth:
- `FIREBASE_PROJECT_ID`, `FIREBASE_API_KEY`, or Firebase Admin SDK credentials

Retrieval pattern (see `src/fetch_transcripts.py`):
```python
security find-generic-password -s "congress-api" -a "$USER" -w
```

## Non-Negotiables

1. **Fail closed**: Missing/unverifiable data -> `NO_DATA` or `ERROR`, never fabricated
2. **Provenance-first**: No downstream signals without source tracking
3. **No demo data in runtime paths**: `config/approved_sources.yaml` enforces allowed sources
4. **Email is selective**: Only `NEW_DOCS` or `ERROR` trigger email alerts. Silence = success.

## Testing

```bash
make test                                                # Run all tests (70% coverage enforced)
./.venv/bin/python -m pytest tests/test_provenance_gate.py -v   # Single file
./.venv/bin/python -m pytest -k "test_name" -v                  # Single test
./.venv/bin/python -m pytest -m "not slow" -v                   # Skip slow tests
./.venv/bin/python -m pytest -m "not integration" -v            # Skip integration tests
```

Test markers: `slow`, `integration`, `e2e`

Tests organized by module: `tests/auth/`, `tests/oversight/`, `tests/signals/`, `tests/state/`, `tests/integration/`

## Code Style

Configured in `pyproject.toml`:
- **Black**: line-length 100, target Python 3.11
- **isort**: black profile
- **Ruff**: E, W, F, I, B, C4, UP rules
- **mypy**: Python 3.11, strict return types

## Deployment

### Docker

```bash
# Dashboard-only (slim, default)
docker build -t va-signals .

# Full image with all dependencies
docker build --build-arg REQUIREMENTS=requirements.txt -t va-signals-full .
```

Runs on port 8080 via uvicorn. Copies `src/`, `schemas/`, `config/`, `migrations/`, `scripts/`, and schema files.

### Cloud Run

- Canary deployment via `.github/workflows/canary-deploy.yml`
- Traffic splitting (e.g., 10% to canary) with health checks and auto-rollback
- Infrastructure scripts in `infrastructure/`:
  - `deploy-cloud-run.sh`, `canary-deploy.sh`
  - `configure-monitoring.sh` (Prometheus)
  - `backup-database.sh`, `restore-database.sh`

### CI/CD Workflows

| Workflow | Purpose |
|----------|---------|
| `daily_fr_delta.yml` | Daily pipeline run + trend aggregation + log cleanup |
| `canary-deploy.yml` | Canary deployment to Cloud Run with traffic splitting |
| `security-scan.yml` | OWASP ZAP + dependency audit + secrets scanning (weekly) |

## Dashboard

Static files in `src/dashboard/static/` (index.html, login.html, app.js, login.js, style.css, login.css). FastAPI serves them and provides `/api/*` endpoints plus WebSocket at `/api/websocket`.

Key API route groups:
- `/api/auth/*` - Authentication
- `/api/tenants/*` - Tenant management
- `/api/ceo-brief/*` - Executive summary
- `/api/evidence/*` - Evidence retrieval
- `/api/battlefield/*` - Gate/calendar data
- `/api/trends/*` - Analytics
- Standard signal/oversight/state endpoints

Run with `make dashboard`, access at `http://localhost:8000`.

## Documentation

- `docs/plans/` - Feature design and implementation plans
- `docs/ops/runbook.md` - Operational runbook
- `docs/governance/AI_USAGE_POLICY.md` - AI usage guidelines
- `docs/DISASTER_RECOVERY.md` - DR procedures
- `docs/DECISIONS.md` - Architecture decision records
- `docs/doctrine/` - System doctrine and principles
