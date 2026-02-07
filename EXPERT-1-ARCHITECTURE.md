# Expert Assessment #1: Systems Architecture & Computer Science Review

**Assessor:** Systems Architect & Computer Scientist
**Date:** 2026-02-07
**Scope:** VA Signals v2 + Vigil + IRON COMPASS
**Method:** Full source-code read of all three codebases, dependency tracing, schema analysis

---

## 1. Architecture Dependency Map

### 1.1 VA Signals v2 Module Dependency Graph

The system has 14 major modules with a clear layered architecture. Dependencies flow downward; violations are flagged.

```
                    +-----------------------+
                    |    dashboard_api.py   |  <-- FastAPI entry point
                    +-----------+-----------+
                                |
          +---------------------+---------------------+
          |         |         |         |              |
     routers/   auth/    tenants/   websocket/    (misc routers)
          |         |         |         |
          +----+----+---------+---------+
               |
    +----------+----------+----------+----------+
    |          |          |          |          |
  ceo_brief/ evidence/ battlefield/ ml/     trends/
    |          |          |          |
    +----------+----------+----------+
               |
    +----------+----------+----------+----------+
    |          |          |          |          |
  signals/  oversight/ state/    agenda_drift.py
    |          |          |
    +----------+----------+
               |
    +----------+----------+
    |          |          |
   db/     resilience/  (fetch_*.py / run_*.py)
    |          |
   core.py  circuit_breaker.py
```

**Critical path modules (everything depends on these):**
- `src/db/core.py:156` -- `connect()` is the single DB entry point for every module
- `src/resilience/circuit_breaker.py` -- all 10 oversight agents depend on it
- `src/resilience/wiring.py` -- sync-to-async bridge used by all fetch modules

**Cross-cutting dependencies (highest fan-in):**
| Module | Depended on by | Role |
|--------|---------------|------|
| `src/db/` | Every module | Data access layer |
| `src/resilience/` | All fetch modules, all oversight agents, all runners | Fault tolerance |
| `src/signals/router.py` | oversight, ceo_brief, run_signals | Signal routing engine |
| `src/notify_email.py` | ceo_brief/runner.py, run_*.py runners | Email delivery |

### 1.2 Cross-Module Import Analysis

**Upward dependency violations (modules reaching up the stack):**

1. **`src/oversight/runner.py:331`** imports `src.signals.correlator.CorrelationEngine` -- oversight reaching into signals. This creates a circular conceptual dependency: signals routes oversight events (via signal_bridge), and oversight calls signals correlator.

2. **`src/ceo_brief/integrations.py:33-345`** imports from `evidence`, `signals.impact`, `battlefield` -- CEO Brief acts as a cross-command aggregator. This is architecturally correct (it's the "Alpha Command" roll-up) but creates the widest import fan-out of any single file (6 modules).

3. **`src/resilience/run_lifecycle.py:48,63,114,138`** imports `src.db` and `src.resilience.circuit_breaker` via deferred imports inside functions. This is correct -- lifecycle is a decorator that wraps runners.

**No circular import cycles detected at the Python module level.** The system uses deferred imports (inside functions) in 4 locations to break potential cycles.

### 1.3 Vigil Module Structure

```
~/.vigil/
  integrations/
    va_signals_bridge.py  --> reads VA Signals signals.db directly
    triage_engine.py      --> reads/writes queue.db
    anchor_pack_generator.py --> reads queue.db, writes YAML packs
    run_pipeline.py       --> orchestrates all three above
    c2_alerts.py          --> reads queue.db, writes C2 outbound
  c2/
    daemon.py             --> Flask webhook server (port 8742)
    executor.py           --> subprocess calls to Claude CLI
    classifier.py         --> intent classification
    security.py           --> auth, rate limiting, scrubbing
    state.py              --> SQLite state DB for messages
    responder.py          --> BlueBubbles message sending
    config.py             --> macOS Keychain + config.json
  heartbeat/
    pulse.sh              --> daily launchd-triggered pipeline
```

**Vigil depends on VA Signals via file-level SQLite reads.** The bridge module (`va_signals_bridge.py:22`) hardcodes an absolute path to `/Users/xa/Work_VC/va-signals-v2/data/signals.db`. There is no API-level integration -- Vigil reads the production database file directly.

---

## 2. Database Schema Analysis

### 2.1 Schema Size and Organization

**51 tables across 14 domains** (verified count from `schema.sql`):

| Domain | Tables | Key Table | Index Count |
|--------|--------|-----------|-------------|
| Core Pipeline | 3 | `source_runs`, `fr_seen`, `ecfr_seen` | 0 (missing!) |
| FR Summaries | 1 | `fr_summaries` | 0 (missing!) |
| Agenda Drift | 5 | `ad_deviation_events` | 0 (missing!) |
| Legislative | 4 | `bills`, `hearings` | 0 (missing!) |
| Oversight | 7 | `om_events` | 4 |
| State Intel | 6 | `state_signals` | 6 |
| Signals Routing | 2 | `signal_audit_log` | 3 |
| Authority | 1 | `authority_docs` | 3 |
| Evidence | 5 | `evidence_packs` | 6 |
| Impact/Heat Map | 4 | `impact_memos` | 5 |
| Battlefield | 6 | `bf_vehicles` | 10 |
| Auth | 3 | `users`, `sessions` | 5 |
| Tenants | 3 | `tenants` | 4 |
| LDA | 2 | `lda_filings` | 3 |
| Trends | 4 | `trend_daily_signals` | 5 |
| Staleness | 1 | `staleness_alerts` | 2 |
| Compound | 1 | `compound_signals` | 3 |

### 2.2 Schema Gaps

**CRITICAL: Missing indices on high-traffic core tables.** The following tables lack indices and will cause full table scans on common queries:

1. **`source_runs`** -- no index on `source_id` or `ended_at`. Every health check and lifecycle query scans the entire table.
   - File: `schema.sql:8-16`
   - Impact: `src/resilience/health_score.py:118-160` queries by source_id repeatedly

2. **`fr_seen`** -- no index on `first_seen_at` or `published_date`. Bridge sync queries by timestamp.
   - File: `schema.sql:18-27`
   - Impact: `va_signals_bridge.py:118` queries `WHERE fs.first_seen_at > ?`

3. **`bills`** -- no index on `updated_at` or `congress`. Bridge sync and API queries need these.
   - File: `schema.sql:109-127`

4. **`hearings`** -- no index on `hearing_date` or `updated_at`.
   - File: `schema.sql:140-156`

5. **`ad_deviation_events`** -- no index on `detected_at` or `zscore`. Bridge sync queries by timestamp.
   - File: `schema.sql:90-103`

**Recommendation:** Add compound indices for the most common query patterns. This is the single highest-ROI change for the entire system.

### 2.3 Normalization Assessment

The schema is generally well-normalized (3NF) with appropriate denormalization for read-heavy patterns:

- **Good:** Foreign keys properly defined across domains
- **Good:** JSON columns used for variable-schema data (`committees_json`, `lobbying_issues_json`)
- **Issue:** `om_events.escalation_signals` stores JSON text -- should be a junction table for queryability
- **Issue:** `compound_signals.member_events` stores JSON text -- cross-referencing requires JSON parsing
- **Issue:** `bf_vehicles` duplicates `heat_score` from `heat_map_issues.score` -- staleness risk

### 2.4 Vigil Database Architecture

Vigil uses 4 separate SQLite databases:
1. `~/.vigil/data/queue.db` -- event queue and sync state (bridge target)
2. `~/.vigil/data/c2.db` -- C2 daemon message state
3. `~/.vigil/data/lda.db` -- LDA lobbying data (separate from VA Signals LDA)
4. `~/.vigil/data/kb-index.db` -- knowledge base index

**This is 5 separate SQLite databases total** (including VA Signals `signals.db`). No shared transaction boundary exists between them. The bridge sync is eventually-consistent with unbounded lag.

---

## 3. API Surface Area

### 3.1 Router Organization

The FastAPI app (`src/dashboard_api.py:106-216`) mounts 16 routers:

| Router | Prefix | Endpoints | Source |
|--------|--------|-----------|--------|
| `health_router` | `/api/` | health, dead-man, staleness | `routers/health.py` |
| `pipeline_router` | `/api/` | runs, stats | `routers/pipeline.py` |
| `summaries_router` | `/api/` | FR summaries | `routers/summaries.py` |
| `reports_router` | `/api/` | daily/weekly reports | `routers/reports.py` |
| `legislative_router` | `/api/` | bills, hearings, LDA | `routers/legislative.py` |
| `state_router` | `/api/` | state signals | `routers/state.py` |
| `oversight_router` | `/api/` | om events, digests | `routers/oversight.py` |
| `agenda_drift_router` | `/api/` | drift detection | `routers/agenda_drift.py` |
| `compound_router` | `/api/` | compound signals | `routers/compound.py` |
| `auth_router` | `/api/auth` | login, sessions | `auth/api.py` |
| `battlefield_router` | `/api/battlefield` | vehicles, calendar, gates | `battlefield/api.py` |
| `ceo_brief_router` | `/api/ceo-brief` | briefs, generate | `ceo_brief/api.py` |
| `evidence_router` | `/api/evidence` | packs, claims, sources | `evidence/dashboard_routes.py` |
| `ml_router` | `/api/ml` | scoring, features | `ml/api.py` |
| `trends_router` | `/api/trends` | analytics | `trends/api.py` |
| `websocket_router` | `/api/websocket` | real-time push | `websocket/api.py` |

**Assessment:**
- Routers are well-organized by domain -- clean separation of concerns
- Consistent RESTful patterns across all routers
- Middleware stack properly layered: CORS -> Auth -> Audit -> Logging (`dashboard_api.py:154-172`)
- OpenAPI documentation is well-tagged with 16 tag groups (`dashboard_api.py:134-151`)

### 3.2 API Concerns

1. **Auth middleware is set to `require_auth=False`** (`dashboard_api.py:163`). This means all endpoints are accessible without authentication by default. Individual endpoints must explicitly check auth. This is intentional for development but a deployment risk.

2. **No API versioning.** All endpoints are at `/api/...` without version prefix. When schema changes occur, there is no way to serve both old and new clients simultaneously.

3. **Prometheus metrics endpoint** (`dashboard_api.py:182-198`) is conditionally available. The graceful fallback is correct, but health endpoints are excluded from instrumentation -- these are often the most useful signals for operations.

---

## 4. Pipeline Orchestration

### 4.1 Runner Architecture

15 pipeline runners with standardized lifecycle:

| Runner | Source ID | Lifecycle Hooks | Fetch Module |
|--------|-----------|----------------|--------------|
| `run_fr_delta.py` | `govinfo_fr_bulk` | Yes | `fr_bulk.py` |
| `run_ecfr_delta.py` | `ecfr_delta` | Yes | (inline) |
| `run_bills.py` | `congress_bills` | Yes | `fetch_bills.py` |
| `run_hearings.py` | `congress_hearings` | Yes | `fetch_hearings.py` |
| `run_oversight.py` | `oversight` | Yes | 10 agent classes |
| `run_lda.py` | `lda_gov` | Yes | `fetch_lda.py` |
| `run_authority_docs.py` | `authority_aggregate` | Yes | 5 fetch_* modules |
| `run_battlefield.py` | `battlefield_sync` | Yes | `battlefield/` |
| `run_agenda_drift.py` | `agenda_drift` | Yes | (multiple) |
| `run_signals.py` | `signals_routing` | Yes | `signals/` |
| `state/runner.py` | per-state | Partial | `state/sources/` |
| `ceo_brief/runner.py` | N/A | No | (aggregator) |

**Lifecycle wrapper** (`src/resilience/run_lifecycle.py:160-214`): Provides `@with_lifecycle(source_id)` decorator that:
1. Pre-check: DB reachable, circuit breaker not OPEN, source in approved list
2. Execute wrapped function
3. Post-check: verify `source_runs` record landed, run canary assertions, check staleness

**Execution graph (dependency order):**
```
Tier 1 (no dependencies):
  run_fr_delta, run_ecfr_delta, run_bills, run_hearings, run_lda
  state/runner (all state sources), run_authority_docs

Tier 2 (depends on Tier 1 data):
  run_oversight (reads external sources, but also uses circuit breakers)
  run_agenda_drift (reads hearings + transcripts)

Tier 3 (aggregates Tier 1+2):
  run_signals (routes events from hearings, bills, om_events)
  run_battlefield (reads bills, hearings, om_events for gate detection)

Tier 4 (synthesizes everything):
  ceo_brief/runner.py (reads FR, bills, hearings, oversight, state)
```

**Runners execute independently via cron/make targets.** There is no orchestrator that ensures Tier 1 completes before Tier 2 starts. In production, the daily cron (`daily_fr_delta.yml`) runs them sequentially, but local `make` targets can fire in any order.

### 4.2 Pipeline Coordination Gap

The oversight runner (`src/oversight/runner.py:280-317`) uses `ThreadPoolExecutor` with `max_workers=len(AGENT_REGISTRY)` (10 threads) to parallelize agents. This works but:

- All 10 agents share a single SQLite connection (WAL mode helps, but write contention is real)
- No backpressure mechanism if one agent produces significantly more events than others
- The correlator (`run_correlation()` at line 314) runs synchronously after all agents finish -- blocking the pipeline even if only low-priority agents have new data

---

## 5. Integration Surface: VA Signals <-> Vigil

### 5.1 Data Flow

```
VA Signals v2                        Vigil
+----------------+                   +------------------+
| signals.db     | -- direct read -> | va_signals_bridge |
|  (51 tables)   |                   |  (6 adapters)     |
+----------------+                   +--------+---------+
                                              |
                                    +--------v---------+
                                    |   queue.db       |
                                    | (queue_events,   |
                                    |  sync_state,     |
                                    |  routing_audit)  |
                                    +--------+---------+
                                              |
                              +---------------+---------------+
                              |               |               |
                    +---------v----+ +--------v------+ +------v--------+
                    | triage_engine| | anchor_pack_  | | c2_alerts.py  |
                    | (score/class)| | generator.py  | | (early warn)  |
                    +---------+----+ +--------+------+ +------+--------+
                              |               |               |
                              |     +---------v-------+       |
                              |     | vnn-anchor-packs/|      |
                              |     | (YAML files)     |      |
                              |     +------------------+      |
                              +-------------------------------+
                                              |
                                    +---------v---------+
                                    | c2/daemon.py      |
                                    | (outbound queue)  |
                                    +-------------------+
                                              |
                                    +---------v---------+
                                    | BlueBubbles/      |
                                    | iMessage           |
                                    +-------------------+
```

### 5.2 Integration Gap Analysis

**Gap 1: Hardcoded absolute path (CRITICAL)**
- File: `~/.vigil/integrations/va_signals_bridge.py:22`
- Code: `VA_SIGNALS_DB = Path("/Users/xa/Work_VC/va-signals-v2/data/signals.db")`
- Impact: Deployment to any other machine, Docker container, or CI breaks the entire integration. This must become an environment variable.

**Gap 2: Direct SQLite file reads bypass all application-level safeguards**
- The bridge reads `signals.db` directly via `sqlite3.connect()`, bypassing:
  - Circuit breakers
  - Rate limiting
  - Auth middleware
  - Audit logging
  - Parameter normalization (`_prepare_query` in db/core.py)
- Risk: If VA Signals is mid-write (even with WAL), the bridge may read partially committed data

**Gap 3: No event acknowledgment or exactly-once delivery**
- The bridge uses `sync_state.last_sync_at` to track progress, but:
  - If the bridge crashes after reading events but before updating `sync_state`, events will be re-synced (duplicates are caught by `IntegrityError` on `event_id`, so functionally OK)
  - If VA Signals inserts events between the bridge's read and sync_state update, events could be missed (race condition window is small but real)

**Gap 4: Triage and anchor pack generation are batch-only**
- The `run_pipeline.py` orchestrator runs synchronously: SYNC -> TRIAGE -> ESCALATION -> PACK_GEN -> ALERTS
- There is no streaming or event-driven trigger. A new HIGH-severity event must wait for the next pipeline run (typically 2x/day per heartbeat schedule)
- IRON COMPASS Phase II requires <24-hour detection latency. The current architecture supports this at 2x/day cadence, but any missed pipeline run doubles the latency to 48 hours.

**Gap 5: C2 daemon is a single point of failure**
- The C2 daemon (`c2/daemon.py`) is a single Flask process on port 8742
- No process manager (systemd, supervisord) -- only a keepalive script and launchd plist
- If the daemon crashes during ORDER execution, recovery happens at next startup (`executor.py:709-789`) but the executor thread cannot be restarted without restarting the whole daemon
- The executor uses `subprocess.run()` to call `claude` CLI -- each ORDER step is a new process with no connection state to prior steps

**Gap 6: Vigil queue.db has no visibility from VA Signals**
- VA Signals has no knowledge of whether Vigil has consumed events. The bridge is one-directional.
- The CEO Brief pipeline cannot include data about Vigil triage status or anchor pack production status
- There is no feedback loop from "event produced" (VA Signals) to "event disseminated" (VNN)

---

## 6. C2 Daemon Architecture Assessment

### 6.1 Architecture

The C2 daemon is a Flask webhook server that receives iMessages via BlueBubbles and routes them through a classifier -> executor pipeline:

```
BlueBubbles -> /webhook -> classify -> {SHORTCUT, ACK, QUERY, ORDER}
                                            |         |        |
                                      (immediate)  (ignore) (enqueue)
                                                              |
                                                    executor thread
                                                              |
                                                    claude CLI subprocess
```

### 6.2 Strengths

1. **Clean message pipeline:** RECV -> AUTH -> RATE -> DEDUP -> CLASSIFY -> EXECUTE -> RESPOND
2. **Security module** (`c2/security.py`): phone normalization, rate limiting (sliding window), input sanitization, outbound scrubbing (API key/SSN/token patterns)
3. **Order decomposition** (`executor.py:31-126`): breaks multi-step orders into max 8 steps, each independently executable
4. **Crash recovery** (`executor.py:709-789`): on startup, finds interrupted orders/messages, marks them failed, notifies commander
5. **Outbound queue** (`daemon.py:308-334`): proactive messages (heartbeat briefs, alerts) are queued and sent asynchronously

### 6.3 Weaknesses

1. **Single-threaded executor:** Only one QUERY or ORDER can execute at a time. The `ExecutorThread` processes the queue sequentially (`executor.py:148-158`). A long-running ORDER blocks all subsequent messages.

2. **No Claude CLI session reuse:** Each query/step spawns a new `subprocess.run()` process (`executor.py:210-223`). There is no conversation continuity between steps within an ORDER (prior outputs are passed via prompt text, not session state).

3. **Flask development server in production:** `app.run()` at `daemon.py:436-441` uses Flask's built-in server. This is single-process, synchronous, and not designed for production workloads. A gunicorn or waitress wrapper would be appropriate.

4. **Global mutable state for rate limiting:** `security.py:84` uses module-level `defaultdict` for rate tracking. This resets on daemon restart and is not thread-safe for concurrent webhook calls.

5. **Host binding to `::`** (`daemon.py:438`): The daemon listens on all interfaces (IPv4 and IPv6). Since BlueBubbles runs on localhost, binding to `127.0.0.1` would be more secure.

---

## 7. IRON COMPASS Sustainability Assessment

### 7.1 Phase I (SET) Requirements vs. Architecture

| Requirement | Current State | Risk |
|------------|--------------|------|
| Federal Register >95% accuracy | FR pipeline functional, no built-in accuracy audit mechanism | LOW -- manual audit feasible |
| VNN 2 packs/week | Pipeline produces packs but requires manual QA gate | MEDIUM -- no automated QA |
| LDA module operational | LDA runner in VA Signals + Vigil integration exists | LOW |
| Pipeline sync >90% uptime | SENTINEL checks health 4x/day; no continuous monitoring | MEDIUM |
| Theater I + II products disseminated | Production pipeline exists end-to-end | LOW |

### 7.2 Phase II (ADVANCE) Requirements vs. Architecture

**IRON COMPASS Tab C (Operations) specifies Phase II as "peak production" with "sustained high tempo" across 3 theaters simultaneously.**

| Stress Factor | Architecture Capacity | Gap |
|--------------|----------------------|-----|
| 2+ VNN packs/week | Pipeline generates packs but each requires Claude CLI subprocess | Throughput limited by Claude API rate limits |
| <24hr detection latency | 2x/day heartbeat pulse + bridge sync | OK if both runs succeed; 48hr if one fails |
| 3 theaters simultaneously | Runners are independent, can execute in parallel | No orchestrator ensures theater-level coordination |
| Commander QA only | Everything below QA is automated | Anchor pack generation is automated; QA is manual review |
| M21-1 change detection | NOT YET BUILT | Gap -- listed as T2-S4 (Mar-Apr) |
| LDA weekly delta reports | LDA runner exists but delta reporting is basic | Functional but needs enrichment |
| Cross-theater correlation | Compound signals correlator exists in VA Signals | Vigil does not consume compound signals |

### 7.3 Key Sustainability Risks

1. **Single-machine dependency:** The entire ecosystem (VA Signals + Vigil + C2) runs on a single macOS machine. No redundancy, no failover.

2. **No scheduled orchestrator:** There is no Airflow, Prefect, or equivalent DAG scheduler. Pipeline execution depends on macOS launchd plists and cron. If the machine sleeps or a plist fails to fire, the entire pipeline stalls silently.

3. **Claude CLI as execution engine:** The C2 daemon and heartbeat both depend on the Claude CLI binary at `/opt/homebrew/bin/claude`. CLI version changes, authentication token expiry, or Anthropic API outages halt all automated intelligence production.

4. **No end-to-end health check:** SENTINEL (`tools/sentinel.py`) checks component health, but there is no single check that validates "an event entered VA Signals and a corresponding anchor pack was generated." The system can appear healthy (all components green) while the integration is silently broken.

---

## 8. Top 5 Architectural Improvements (Ranked by Leverage)

### #1: Add Missing Database Indices (HIGH leverage, LOW effort)

**What:** Add indices to `source_runs`, `fr_seen`, `bills`, `hearings`, and `ad_deviation_events`.

**Why:** These are the most-queried tables and currently require full table scans. As data accumulates, query performance degrades linearly. The bridge sync, health score computation, and API queries all hit these tables.

**Where:** `schema.sql` lines 8-16, 18-27, 109-127, 140-156, 90-103.

**Suggested indices:**
```sql
CREATE INDEX IF NOT EXISTS idx_source_runs_source ON source_runs(source_id, ended_at);
CREATE INDEX IF NOT EXISTS idx_fr_seen_first_seen ON fr_seen(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_bills_updated ON bills(updated_at);
CREATE INDEX IF NOT EXISTS idx_bills_congress ON bills(congress);
CREATE INDEX IF NOT EXISTS idx_hearings_date ON hearings(hearing_date);
CREATE INDEX IF NOT EXISTS idx_hearings_updated ON hearings(updated_at);
CREATE INDEX IF NOT EXISTS idx_ad_deviations_detected ON ad_deviation_events(detected_at);
```

### #2: Replace Hardcoded Bridge Path with API Integration (HIGH leverage, MEDIUM effort)

**What:** Replace the direct SQLite file read in `va_signals_bridge.py:22` with either:
- (a) Environment variable for path (quick fix), or
- (b) HTTP API calls to VA Signals FastAPI endpoints (correct fix)

**Why:** The hardcoded path breaks deployment portability, bypasses all application safeguards, and creates a hidden coupling. Using the FastAPI API would give the bridge circuit breakers, rate limiting, auth, and audit for free.

**Where:** `~/.vigil/integrations/va_signals_bridge.py:22` and all 6 adapter classes.

### #3: Build Pipeline DAG Orchestrator (HIGH leverage, HIGH effort)

**What:** Create a lightweight DAG scheduler that ensures Tier 1 runners complete before Tier 2, and Tier 2 before Tier 3. Could be as simple as a Python script that runs runners in dependency order and tracks completion.

**Why:** Currently, runners execute independently with no coordination. In IRON COMPASS Phase II, running signals routing before overnight data arrives produces stale analysis. The CEO Brief pipeline cannot guarantee it has the latest data.

**Where:** New module, potentially `src/orchestrator.py` or extending `Makefile` with dependency chains.

### #4: Add End-to-End Health Check (MEDIUM leverage, LOW effort)

**What:** Build a health check that traces an event through: VA Signals ingestion -> bridge sync -> queue.db -> triage -> anchor pack generation. Verify each stage within expected SLA.

**Why:** The current health checks are component-level (DB reachable, circuit breaker state, source freshness). They cannot detect integration failures where individual components are healthy but the pipeline is broken.

**Where:** Extend `~/.vigil/tools/sentinel.py` or build new `integration_health.py` that queries both `signals.db` and `queue.db`.

### #5: Add Event-Driven Bridge Trigger (MEDIUM leverage, MEDIUM effort)

**What:** When a HIGH-severity event is inserted into `om_events` or `signal_audit_log`, trigger an immediate bridge sync + triage rather than waiting for the next scheduled pipeline run.

**Why:** IRON COMPASS requires <24-hour detection latency. The current 2x/day batch sync meets this under normal conditions but has no way to expedite urgent events. An inotify/polling mechanism or database trigger could cut latency from hours to minutes.

**Where:** Could be implemented as a post-insert hook in `src/oversight/runner.py:240-252` that sends an HTTP request to Vigil's pipeline, or as a SQLite trigger + file watcher.

---

## 9. Summary Verdict

The VA Signals v2 + Vigil architecture is **production-grade for a single-operator intelligence system**. The code quality is high: consistent patterns, proper error handling, well-organized modules, and comprehensive schema design. The resilience layer (circuit breakers, lifecycle hooks, canary assertions, health scoring) is sophisticated for a system of this size.

**The primary architectural risk is the integration boundary between VA Signals and Vigil.** The direct SQLite file read, batch-only sync, and lack of end-to-end health checking create a fragile coupling that is invisible to component-level monitoring.

**For IRON COMPASS Phase I (SET),** the architecture is sufficient. The pipeline exists end-to-end, and the 2x/day cadence meets the <24-hour latency requirement.

**For IRON COMPASS Phase II (ADVANCE),** the architecture will be stressed by the sustained high-tempo requirement. The single-machine dependency, lack of orchestration, and manual QA gate are the primary bottlenecks. The system can sustain 2 packs/week, but 3+ packs/week or multi-theater simultaneous operations will require automation of the QA gate and more robust pipeline scheduling.

**The database index gap is the single highest-ROI fix.** It requires no architectural changes, can be deployed immediately, and will improve performance across every module that queries the database.
