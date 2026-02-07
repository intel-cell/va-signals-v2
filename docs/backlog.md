# VA Signals v2 — Backlog

> Generated: 2026-02-06 | Source: 10-agent multi-perspective assessment
> Campaign Plan: docs/plans/2026-01-22-operational-design-campaign-plan.md

---

## Sprint 1 (Complete — 2026-02-06)
- [x] Wire ML router into dashboard API
- [x] Inject ML scoring into oversight escalation pipeline
- [x] Add CEO Brief Makefile target + crontab entry
- [x] Parallelize oversight runner with ThreadPoolExecutor

## Sprint 2 (Complete — 2026-02-06)
- [x] Parallelize state runner with ThreadPoolExecutor
- [x] Create regulatory_change.yaml signal schema
- [x] Create claims_operations.yaml signal schema
- [x] Create legislative_action.yaml signal schema
- [x] Add email SMTP health check endpoint
- [x] Implement dead-man's switch (48h zero signals alert)

## Sprint 3 (Complete — 2026-02-05)
- [x] Phase I: All 9 oversight agents operational
- [x] 90-day baseline computation (8/9 sources baselined)
- [x] Auth hardening (Cloud Run rev 34, 60 tests passing)
- [x] CI/CD pipeline updated with oversight + state monitor

## Sprint 4 (Complete — 2026-02-05)
- [x] Phase II: PA, OH, NY state sources added
- [x] Cross-source correlator module created
- [x] Database modularized (db.py split into 8 domain modules)
- [x] Dashboard API refactored into 8 sub-routers

## Sprint 5 (Complete — 2026-02-05)
- [x] Phase III: NC, GA, VA, AZ state sources added (10/10 states)
- [x] Staleness detection system added
- [x] 10th oversight agent (BVA) added
- [x] Trend aggregation pipeline operational

---

## Sprint 6 — STABILIZE (Current)

**Theme:** "Make what's built actually work."
**Goal:** Eliminate silent failures, wire disconnected modules, fix security gaps, sync schemas.
**Duration:** ~9 days | **Phase:** IV (Sustainment)

### T1: Fix WebSocket auth bypass + CORS tightening
- **Priority:** CRITICAL (Security)
- **Files:** `src/websocket/api.py`, `src/dashboard_api.py`
- **Details:**
  - WebSocket endpoint accepts optional `token` param with no verification (api.py:31-72)
  - Line 72 fakes user extraction: `user_id = f"user_{token[:8]}"` — no crypto validation
  - CORS allows `methods=["*"]` and `headers=["*"]` (dashboard_api.py:161-167)
- **Acceptance:**
  - WebSocket connections require valid Firebase token via middleware
  - CORS restricted to explicit methods and headers
  - Incoming WebSocket messages re-validate auth

### T2: Wire resilience module into all fetch modules
- **Priority:** HIGH (Architecture + Data Pipeline)
- **Files:** `src/resilience/circuit_breaker.py`, `src/resilience/rate_limiter.py`, all `src/fetch_*.py`, `src/oversight/agents/*.py`
- **Details:**
  - Circuit breaker, rate limiter, retry modules exist (28 KB, tested) but ZERO production imports
  - Fetch modules use bare `requests.get()` or `urllib3.util.retry` inconsistently
  - No timeout enforcement in HTML scrapers; Playwright hardcoded at 30s
- **Acceptance:**
  - All `fetch_*` modules wrapped with circuit breaker decorator
  - Oversight agents use rate limiter for external HTTP calls
  - Global 45s timeout on all scraper calls
  - Circuit breaker state visible on `/api/health` endpoint

### T3: Implement staleness SLA monitoring + alerting
- **Priority:** HIGH (Eliminates "failed silence")
- **Files:** `src/routers/health.py`, `src/oversight/staleness_monitor.py`, new: `config/source_sla.yaml`
- **Details:**
  - System can log SUCCESS with zero actionable data — indistinguishable from "nothing new"
  - `staleness_alerts` table exists (migration 007) but never written to
  - No expected-freshness SLA per source
  - 52% of pipeline runs return NO_DATA; 21.5% ERROR — no alerting on these rates
- **Acceptance:**
  - `config/source_sla.yaml` defines expected freshness per source (FR=1h, GAO=1d, State=6h, etc.)
  - Health endpoint checks `MAX(ended_at)` against SLA and triggers alert if exceeded
  - `staleness_alerts` table populated on SLA violation
  - Dashboard shows source health with green/yellow/red status
  - Alert fires if >50% of runs in 24h are NO_DATA or ERROR

### T4: Integrate cross-source correlator into escalation pipeline
- **Priority:** HIGH (Alert precision 90% -> 95%)
- **Files:** `src/signals/correlator.py`, `src/oversight/pipeline/escalation.py`, `src/oversight/runner.py`
- **Details:**
  - Correlator module (488 LOC) built last week but not integrated into main pipeline
  - GAO report + NewsAPI headline about same event = 2 separate om_events rows
  - Current dedup only catches same report ID; no fuzzy/cross-source matching
  - Alert precision at ~90%, target >95%
- **Acceptance:**
  - Correlator called after dedup step in oversight pipeline
  - Cross-source events linked via `canonical_refs` column
  - Fuzzy title matching across sources (threshold: 0.85 similarity)
  - Test with existing om_events corpus showing dedup improvement
  - Alert precision measurably improved (track in source_runs metadata)

### T5: Sync SQLite/PostgreSQL schemas + enforce WAL in tests
- **Priority:** HIGH (Architecture + Testing)
- **Files:** `schema.sql`, `schema.postgres.sql`, `tests/conftest.py`, `pyproject.toml`
- **Details:**
  - PostgreSQL has 57 tables, SQLite has 54 — missing: tenants, tenant_members, tenant_settings
  - Migration 004 exists but schema.sql not updated
  - WAL mode only enforced in 1 test file (test_correlator.py); rest risk "database locked"
  - Coverage floor quietly dropped from 70% to 35%
- **Acceptance:**
  - `schema.sql` updated with all 57 tables matching PostgreSQL
  - `conftest.py` autouse fixture enables `PRAGMA journal_mode=WAL` for all SQLite tests
  - `pyproject.toml` coverage floor bumped to 45% (ratchet up each sprint)
  - All tests pass with WAL enabled

### T6: Add CI failure notifications + remove continue-on-error
- **Priority:** HIGH (DevOps)
- **Files:** `.github/workflows/daily_fr_delta.yml`, `.github/workflows/security-scan.yml`
- **Details:**
  - Daily pipeline uses `continue-on-error: true` — failures are silent
  - Security scan sets `fail_action: false` — reports generate but don't block
  - No notification on pipeline failure; operators must manually check artifacts
  - Canary deploy is manual with no auto-promotion
- **Acceptance:**
  - `continue-on-error` removed from critical pipeline steps (FR, eCFR, oversight, state)
  - Security scan `fail_action` set to `warn` (generates issue, doesn't block)
  - Failure notification step added (GitHub → email on workflow failure)
  - Pipeline health visible on dashboard via source_runs query

---

## Sprint 7 (Planned — Pending Sprint 6 completion)

**Theme:** "Expand value from stable foundation."

- [ ] Wire signals routing engine into oversight/legislative pipelines (or deprecate)
- [ ] Expand ML scoring to evidence ranking + CEO brief prioritization
- [ ] Automate CEO Brief → Slack push (top 3 signals at 7am)
- [ ] Add auto-retry decorator to all cron runners (exponential backoff)
- [ ] State scraper resilience: save HTML snapshots, test against 6-month-old markup
- [ ] Evidence pipeline testing (currently 0% coverage)
- [ ] Tenant isolation integration tests
- [ ] Bump coverage floor to 55%

## Sprint 8 (Planned)

**Theme:** "Close the <5 min/day contract."

- [ ] Dashboard live-update via WebSocket (replace manual log checking)
- [ ] Canary auto-promotion schedule (10% → 25% → 50% → 100% over 2h)
- [ ] Cross-source dedup: fuzzy title+date hashing across bills/oversight/news
- [ ] Continuous post-deploy health monitoring
- [ ] Monthly backup restore test (documented runbook)

---

## Assessment Sources (2026-02-06)

This backlog was derived from a 10-agent simultaneous assessment:

| Assessor | Key Finding |
|----------|-------------|
| Red Hat (Gut) | "Premature architecture" — building plumbing faster than water flows |
| Green Hat (Innovation) | 80% complete, needs integration not invention |
| Yellow Hat (Optimist) | Domain knowledge + operational discipline uniquely valuable |
| Black Hat (Pessimist) | "Failed silence" — system appears healthy while blind |
| Pragmatic (Blue Hat) | Freeze features, execute 6 tasks, hit <5 min/day |
| Security Expert | WebSocket auth bypass, CORS, tenant SQL injection, hardcoded dev secret |
| Architecture Expert | Signals routing disconnected, schema drift, resilience unused |
| Testing Expert | 267 real tests (not 655), coverage at 35% floor, evidence/tenant untested |
| DevOps Expert | Level 3 maturity, CI failures silent, canary manual, backups untested |
| Data Pipeline Expert | 70% production-ready, cross-source dedup missing, scrapers fragile |
