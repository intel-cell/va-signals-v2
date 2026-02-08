# Test Coverage Analysis

**Date**: 2026-02-07
**Overall Coverage**: 67% (16,367 statements, 4,877 missed)
**Tests**: 2,036 passed, 1 failed, 22 skipped
**Enforced Minimum**: 55% | **Target**: 70%

## Coverage by Module (files below 55%)

| Module | Coverage | Stmts | Missed | Risk |
|--------|----------|-------|--------|------|
| `src/embed_utterances.py` | 0% | 84 | 84 | Medium |
| `src/fr_details.py` | 0% | 77 | 77 | Medium |
| `src/fetch_va_pubs.py` | 9% | 143 | 123 | High |
| `src/fetch_reginfo_pra.py` | 10% | 137 | 116 | Medium |
| `src/trends/aggregator.py` | 12% | 96 | 83 | High |
| `src/trends/queries.py` | 13% | 95 | 81 | High |
| `src/fetch_omb_guidance.py` | 12% | 105 | 87 | Medium |
| `src/fetch_omb_internal_drop.py` | 12% | 80 | 66 | Medium |
| `src/fetch_whitehouse.py` | 16% | 118 | 93 | Medium |
| `src/fetch_transcripts.py` | 16% | 214 | 170 | Medium |
| `src/summarize.py` | 17% | 261 | 205 | High |
| `src/signals/adapters/bf_alerts.py` | 18% | 33 | 25 | Medium |
| `src/fr_bulk.py` | 18% | 91 | 70 | Medium |
| `src/evidence/delta_integration.py` | 19% | 135 | 104 | High |
| `src/agenda_drift.py` | 19% | 125 | 95 | Medium |
| `src/battlefield/integrations.py` | 23% | 59 | 42 | Medium |
| `src/battlefield/calendar.py` | 26% | 160 | 108 | High |
| `src/signals/impact/db.py` | 27% | 134 | 95 | High |
| `src/fetch_hearings.py` | 27% | 181 | 120 | Medium |
| `src/routers/summaries.py` | 29% | 83 | 55 | Medium |
| `src/resilience/api.py` | 31% | 80 | 50 | Medium |
| `src/ceo_brief/runner.py` | 34% | 137 | 84 | Medium |
| `src/fetch_bills.py` | 37% | 229 | 135 | Medium |
| `src/ml/api.py` | 38% | 76 | 40 | Medium |
| `src/ceo_brief/integrations.py` | 39% | 172 | 100 | High |
| `src/routers/agenda_drift.py` | 38% | 80 | 47 | Medium |
| `src/websocket/broadcast.py` | 42% | 39 | 20 | Medium |
| `src/routers/reports.py` | 43% | 19 | 9 | Low |
| `src/auth/api.py` | 49% | 269 | 127 | Critical |
| `src/ml/scoring.py` | 50% | 153 | 62 | Medium |
| `src/battlefield/api.py` | 52% | 112 | 48 | Medium |
| `src/ceo_brief/db_helpers.py` | 52% | 147 | 60 | Medium |
| `src/auth/rbac.py` | 53% | 149 | 61 | Critical |
| `src/ceo_brief/generator.py` | 53% | 156 | 60 | Medium |
| `src/websocket/manager.py` | 54% | 103 | 42 | Medium |
| `src/evidence/extractors.py` | 54% | 240 | 104 | Medium |

## Priority Improvement Areas

### Priority 1: Auth API + RBAC (Critical Security)

- `src/auth/api.py` (49%) - Login, token verification, session management half-tested
- `src/auth/rbac.py` (53%) - Role enforcement functions uncovered
- `src/auth/audit.py` (65%) - Compliance/export paths untested

**Action**: Test every auth failure mode, every role-permission combination, audit query paths.

### Priority 2: Trends & Analytics (12-13%)

- `src/trends/aggregator.py` (12%) - Dashboard analytics computation
- `src/trends/queries.py` (13%) - All SQL query functions uncovered

**Action**: Mock DB, verify SQL generation and result shaping.

### Priority 3: Data Fetchers (9-37%)

Eight fetcher modules averaging ~20% coverage. All make HTTP calls to government APIs.

**Action**: Add fixture-based tests with mocked HTTP responses for success, malformed data, and error cases.

### Priority 4: CEO Brief Pipeline (34-53%)

- `src/ceo_brief/runner.py` (34%)
- `src/ceo_brief/integrations.py` (39%)
- `src/ceo_brief/db_helpers.py` (52%)
- `src/ceo_brief/generator.py` (53%)

**Action**: Test runner with mocked sub-components. Snapshot tests for generator output.

### Priority 5: Battlefield Calendar + Impact DB (23-27%)

- `src/battlefield/calendar.py` (26%) - 108 missed statements
- `src/signals/impact/db.py` (27%) - 95 missed statements

**Action**: Test gate detection, date boundaries, and impact CRUD operations.

## Projected Impact

| # | Action | Current | Target | Lines Recovered |
|---|--------|---------|--------|-----------------|
| 1 | Auth + RBAC | 49-53% | 90% | ~130 |
| 2 | Trends | 12-13% | 80% | ~130 |
| 3 | Data fetchers (8 files) | 9-37% | 70% | ~500 |
| 4 | CEO brief pipeline | 34-39% | 75% | ~130 |
| 5 | Impact DB + battlefield | 26-27% | 75% | ~150 |
| **Total** | | | | **~1,040 lines** |

Recovering these lines would push overall coverage from **67% to ~73%**, past the 70% target.

## Other Issues

1. **Failing test**: `tests/tenants/test_middleware.py::TestResolveTenantWithHeaders::test_non_member_gets_403`
2. **Coverage threshold**: Enforced at 55%, should ratchet to 65%
3. **Oversight agents**: Most agents besides `bva` (94%) and `news_wire` (93%) have poor coverage
4. **Router tests**: Most router coverage is indirect; dedicated unit tests needed
