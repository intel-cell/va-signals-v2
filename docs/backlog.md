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

## Sprint 6 — STABILIZE (Complete — 2026-02-07)

**Theme:** "Make what's built actually work."
**Results:** 1,397 tests passing (+32), coverage 45% → 54%, zero regressions.

- [x] T1: WebSocket auth hardened — periodic token expiry recheck (4401) + rate limiting 30/min (4429)
- [x] T2: Resilience wiring verified — parametrized tests confirm all 10 fetch modules use circuit breakers
- [x] T3: Staleness persistence activated — `persist_alert()` wired into `post_run_check()` lifecycle hook
- [x] T4: Correlator integration tested — 6 tests covering legislative-oversight, state divergence, title similarity
- [x] T5: Schema parity enforced — automated test prevents SQLite/PostgreSQL drift (57 tables synced)
- [x] T6: CI documentation — `continue-on-error` on SARIF upload documented as intentional

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
