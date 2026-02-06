# Sprint 1: Wiring & Parallelization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire the disconnected ML scoring module into the oversight pipeline and dashboard API, automate CEO Brief generation via Makefile, and parallelize the oversight runner for 3-5x speedup.

**Architecture:** The ML module (1,049 lines in `src/ml/`) is fully implemented but its FastAPI router was never registered in `dashboard_api.py` and its `SignalScorer` is never called during event processing. We register the router (1 line), inject ML scoring into the oversight escalation pipeline (augmenting `check_escalation` in `src/oversight/pipeline/escalation.py`), add a CEO Brief Makefile target + crontab entry, and convert the oversight runner's blocking for-loop to `concurrent.futures.ThreadPoolExecutor`.

**Tech Stack:** Python 3.11, FastAPI, concurrent.futures, pytest, existing resilience decorators

---

## Task 1: Wire ML Router into Dashboard API

**Files:**
- Modify: `src/dashboard_api.py:441` (after CEO Brief router include)
- Test: `tests/test_ml_router_registration.py` (create)

**Step 1: Write the failing test**

Create `tests/test_ml_router_registration.py`:

```python
"""Test that ML scoring API routes are registered in the dashboard."""

from fastapi.testclient import TestClient


def test_ml_routes_registered():
    """ML router should be included in the main FastAPI app."""
    from src.dashboard_api import app

    route_paths = [r.path for r in app.routes]
    assert "/api/ml/score" in route_paths, "ML score endpoint not registered"
    assert "/api/ml/config" in route_paths, "ML config endpoint not registered"
    assert "/api/ml/stats" in route_paths, "ML stats endpoint not registered"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/xa/Work_VC/va-signals-v2 && ./.venv/bin/python -m pytest tests/test_ml_router_registration.py -v`
Expected: FAIL with `AssertionError: ML score endpoint not registered`

**Step 3: Write minimal implementation**

In `src/dashboard_api.py`, add the import near the other router imports (around line 39-41):

```python
from .ml.api import router as ml_router
```

Then add the router include after line 441 (after `app.include_router(ceo_brief_router)`):

```python
# Include ML scoring router
app.include_router(ml_router)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/xa/Work_VC/va-signals-v2 && ./.venv/bin/python -m pytest tests/test_ml_router_registration.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /Users/xa/Work_VC/va-signals-v2
git add tests/test_ml_router_registration.py src/dashboard_api.py
git commit -m "feat: wire ML scoring router into dashboard API"
```

---

## Task 2: Inject ML Scoring into Oversight Escalation

**Files:**
- Modify: `src/oversight/pipeline/escalation.py`
- Modify: `src/oversight/runner.py:70-136` (the `_process_raw_event` function)
- Test: `tests/oversight/test_pipeline/test_escalation.py` (modify existing)

**Context:** The current `check_escalation()` function does keyword/phrase matching only. We add an optional ML scoring step that enriches the `EscalationResult` with a numeric score and risk level. The ML scorer is imported lazily to avoid breaking anything if ML deps are missing.

**Step 1: Write the failing test**

Add to `tests/oversight/test_pipeline/test_escalation.py`:

```python
def test_escalation_includes_ml_score():
    """check_escalation should include ml_score and ml_risk_level fields."""
    result = check_escalation(
        title="GAO audit of VA disability claims backlog",
        content="The Government Accountability Office found systemic delays in processing veteran disability claims.",
    )
    assert hasattr(result, "ml_score"), "EscalationResult missing ml_score"
    assert hasattr(result, "ml_risk_level"), "EscalationResult missing ml_risk_level"
    assert isinstance(result.ml_score, (float, type(None)))
    assert isinstance(result.ml_risk_level, (str, type(None)))
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/xa/Work_VC/va-signals-v2 && ./.venv/bin/python -m pytest tests/oversight/test_pipeline/test_escalation.py::test_escalation_includes_ml_score -v`
Expected: FAIL with `AttributeError: 'EscalationResult' has no attribute 'ml_score'`

**Step 3: Write minimal implementation**

Replace the full contents of `src/oversight/pipeline/escalation.py`:

```python
"""Escalation signal checker for oversight events."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from src.oversight.db_helpers import get_active_escalation_signals

logger = logging.getLogger(__name__)


@dataclass
class EscalationResult:
    """Result of escalation check."""

    is_escalation: bool
    matched_signals: list[str] = field(default_factory=list)
    severity: str = "none"  # critical, high, medium, none
    ml_score: Optional[float] = None
    ml_risk_level: Optional[str] = None


def _try_ml_score(title: str, content: str) -> tuple[Optional[float], Optional[str]]:
    """Attempt ML scoring. Returns (score, risk_level) or (None, None) on failure."""
    try:
        from src.ml import SignalScorer

        scorer = SignalScorer()
        result = scorer.score({"title": title, "content": content, "source_type": "oversight"})
        return result.overall_score, result.risk_level.value
    except Exception as e:
        logger.debug(f"ML scoring unavailable: {e}")
        return None, None


def check_escalation(title: str, content: str) -> EscalationResult:
    """
    Check if text contains escalation signals.

    Args:
        title: Event title
        content: Event content/excerpt

    Returns:
        EscalationResult with matched signals and optional ML score
    """
    signals = get_active_escalation_signals()

    combined_text = f"{title} {content}".lower()
    matched = []
    max_severity = "none"
    severity_order = {"critical": 3, "high": 2, "medium": 1, "none": 0}

    for signal in signals:
        pattern = signal["signal_pattern"].lower()
        signal_type = signal["signal_type"]

        # Check for match based on signal type
        if signal_type == "keyword":
            # Word boundary match for keywords
            if re.search(rf"\b{re.escape(pattern)}\b", combined_text):
                matched.append(pattern)
                if severity_order.get(signal["severity"], 0) > severity_order.get(max_severity, 0):
                    max_severity = signal["severity"]

        elif signal_type == "phrase":
            # Substring match for phrases
            if pattern in combined_text:
                matched.append(pattern)
                if severity_order.get(signal["severity"], 0) > severity_order.get(max_severity, 0):
                    max_severity = signal["severity"]

    # Enrich with ML scoring
    ml_score, ml_risk_level = _try_ml_score(title, content)

    return EscalationResult(
        is_escalation=len(matched) > 0,
        matched_signals=matched,
        severity=max_severity,
        ml_score=ml_score,
        ml_risk_level=ml_risk_level,
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/xa/Work_VC/va-signals-v2 && ./.venv/bin/python -m pytest tests/oversight/test_pipeline/test_escalation.py -v`
Expected: ALL PASS (existing tests should still pass since we only added optional fields)

**Step 5: Commit**

```bash
cd /Users/xa/Work_VC/va-signals-v2
git add src/oversight/pipeline/escalation.py tests/oversight/test_pipeline/test_escalation.py
git commit -m "feat: inject ML scoring into oversight escalation pipeline"
```

---

## Task 3: Propagate ML Score to Oversight Event Output

**Files:**
- Modify: `src/oversight/runner.py:70-136` (the `_process_raw_event` function)
- Test: `tests/oversight/test_runner.py` (add test)

**Context:** The runner calls `check_escalation()` and stores `is_escalation` and `escalation_signals` on the event dict. We now also store `ml_score` and `ml_risk_level` from the enriched `EscalationResult`.

**Step 1: Read the current _process_raw_event to find where escalation result is consumed**

Read `src/oversight/runner.py` lines 70-136 to find the exact lines that access `EscalationResult` fields. Look for where `escalation_result.is_escalation` and `escalation_result.matched_signals` are stored into the event dict.

**Step 2: Write the failing test**

Add to `tests/oversight/test_runner.py`:

```python
def test_processed_event_includes_ml_fields(monkeypatch):
    """Processed events should include ml_score and ml_risk_level."""
    from src.oversight.pipeline.escalation import EscalationResult

    # Mock check_escalation to return known ML values
    mock_result = EscalationResult(
        is_escalation=False,
        matched_signals=[],
        severity="none",
        ml_score=0.72,
        ml_risk_level="HIGH",
    )
    monkeypatch.setattr(
        "src.oversight.runner.check_escalation",
        lambda title, content: mock_result,
    )

    # We need to test that _process_raw_event propagates ml fields.
    # The exact test setup depends on the function signature found in Step 1.
    # This test skeleton will be refined during execution.
```

**Step 3: Add ml_score and ml_risk_level to the event dict**

In `src/oversight/runner.py`, find the block where the event dict is built (approx lines 100-130). Add after the `escalation_signals` line:

```python
"ml_score": escalation_result.ml_score,
"ml_risk_level": escalation_result.ml_risk_level,
```

**Step 4: Run tests**

Run: `cd /Users/xa/Work_VC/va-signals-v2 && ./.venv/bin/python -m pytest tests/oversight/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
cd /Users/xa/Work_VC/va-signals-v2
git add src/oversight/runner.py tests/oversight/test_runner.py
git commit -m "feat: propagate ML score through oversight event pipeline"
```

---

## Task 4: Add CEO Brief Makefile Target

**Files:**
- Modify: `Makefile`
- Test: Manual — run `make ceo-brief-dry` and verify output

**Step 1: Verify existing CLI runner works**

Run: `cd /Users/xa/Work_VC/va-signals-v2 && ./.venv/bin/python -m src.ceo_brief.runner --help 2>&1 || ./.venv/bin/python -m src.ceo_brief.runner --dry-run 2>&1 | head -20`

Check what flags the runner accepts. The runner at `src/ceo_brief/runner.py` line ~340 has `if __name__ == "__main__"` with argparse.

**Step 2: Add Makefile targets**

Append to the Makefile, after the `authority-docs` target:

```makefile
# CEO Brief Generation
ceo-brief:
	ANTHROPIC_API_KEY=$$(security find-generic-password -s "claude-api" -a "$$USER" -w) \
	./.venv/bin/python -m src.ceo_brief.runner

ceo-brief-dry:
	./.venv/bin/python -m src.ceo_brief.runner --dry-run
```

**Step 3: Test the dry-run target**

Run: `cd /Users/xa/Work_VC/va-signals-v2 && make ceo-brief-dry`
Expected: Runs without error, prints brief info without writing or calling LLM

**Step 4: Add to .crontab**

Add after line 20 of `.crontab`:

```
# CEO Brief (daily at 7am, after all sources have run)
0 7 * * * . /Users/xa/Work_VC/va-signals-v2/.env.cron && cd /Users/xa/Work_VC/va-signals-v2 && make ceo-brief >> /tmp/va-signals-cron.log 2>&1
```

**Step 5: Commit**

```bash
cd /Users/xa/Work_VC/va-signals-v2
git add Makefile .crontab
git commit -m "feat: add CEO Brief Makefile target + daily cron automation"
```

---

## Task 5: Parallelize Oversight Runner

**Files:**
- Modify: `src/oversight/runner.py:228-246` (the `run_all_agents` function)
- Test: `tests/oversight/test_runner.py` (add parallelization test)

**Context:** The current `run_all_agents()` runs 9 agents sequentially in a blocking for-loop. Each agent does I/O-bound work (RSS feeds, HTTP requests). We use `concurrent.futures.ThreadPoolExecutor` because the agents are synchronous code doing I/O. The existing circuit breakers and retry decorators are async but the agents themselves are sync.

**Step 1: Write the failing test**

Add to `tests/oversight/test_runner.py`:

```python
import time
from unittest.mock import patch, MagicMock
from src.oversight.runner import run_all_agents, OversightRunResult


def test_run_all_agents_parallelism():
    """run_all_agents should run agents concurrently, not sequentially.

    If 9 agents each take 0.1s, sequential = ~0.9s, parallel < 0.4s.
    """
    def slow_agent(agent_name, since=None):
        time.sleep(0.1)
        return OversightRunResult(
            agent=agent_name,
            status="SUCCESS",
            events_fetched=0,
            events_processed=0,
        )

    with patch("src.oversight.runner.run_agent", side_effect=slow_agent):
        start = time.monotonic()
        results = run_all_agents()
        elapsed = time.monotonic() - start

    assert len(results) == 9, f"Expected 9 results, got {len(results)}"
    assert elapsed < 0.5, f"Took {elapsed:.2f}s — agents likely running sequentially"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/xa/Work_VC/va-signals-v2 && ./.venv/bin/python -m pytest tests/oversight/test_runner.py::test_run_all_agents_parallelism -v`
Expected: FAIL with `AssertionError: Took ~0.9Xs — agents likely running sequentially`

**Step 3: Write minimal implementation**

Replace `run_all_agents` in `src/oversight/runner.py` (lines 228-246):

```python
def run_all_agents(since: Optional[datetime] = None) -> list[OversightRunResult]:
    """
    Run all registered oversight agents in parallel.

    Uses ThreadPoolExecutor for concurrent I/O-bound agent execution.

    Args:
        since: Only fetch events since this time

    Returns:
        List of results for each agent (order matches AGENT_REGISTRY)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[str, OversightRunResult] = {}

    with ThreadPoolExecutor(max_workers=len(AGENT_REGISTRY)) as executor:
        future_to_agent = {
            executor.submit(run_agent, agent_name, since): agent_name
            for agent_name in AGENT_REGISTRY
        }

        for future in as_completed(future_to_agent):
            agent_name = future_to_agent[future]
            try:
                result = future.result()
                results[agent_name] = result
                logger.info(f"[{agent_name}] {result.status}: {result.events_processed} processed")
            except Exception as e:
                logger.error(f"[{agent_name}] Thread failed: {e}")
                results[agent_name] = OversightRunResult(
                    agent=agent_name,
                    status="ERROR",
                    errors=[f"Thread exception: {repr(e)}"],
                )

    # Return in registry order for deterministic output
    return [results[name] for name in AGENT_REGISTRY]
```

**Step 4: Run tests**

Run: `cd /Users/xa/Work_VC/va-signals-v2 && ./.venv/bin/python -m pytest tests/oversight/test_runner.py -v`
Expected: ALL PASS, parallelism test under 0.5s

**Step 5: Run full test suite to check for regressions**

Run: `cd /Users/xa/Work_VC/va-signals-v2 && ./.venv/bin/python -m pytest -x -q`
Expected: No regressions

**Step 6: Commit**

```bash
cd /Users/xa/Work_VC/va-signals-v2
git add src/oversight/runner.py tests/oversight/test_runner.py
git commit -m "perf: parallelize oversight runner with ThreadPoolExecutor (9 agents)"
```

---

## Task 6: Add ML Score Fields to om_events Schema

**Files:**
- Create: `migrations/006_add_ml_score_columns.py`
- Modify: `schema.sql` (add columns to om_events)
- Modify: `schema.postgres.sql` (add columns to om_events)
- Test: `tests/test_migration_script.py` (add test)

**Context:** The om_events table needs `ml_score REAL` and `ml_risk_level TEXT` columns so the ML enrichment from Task 2-3 actually persists to the database.

**Step 1: Write the migration**

Create `migrations/006_add_ml_score_columns.py`:

```python
"""Add ML scoring columns to om_events table."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import connect, execute


def migrate():
    con = connect()
    try:
        execute(con, "ALTER TABLE om_events ADD COLUMN ml_score REAL")
    except Exception:
        pass  # Column already exists
    try:
        execute(con, "ALTER TABLE om_events ADD COLUMN ml_risk_level TEXT")
    except Exception:
        pass  # Column already exists
    con.commit()
    print("Migration 006: Added ml_score and ml_risk_level to om_events")


if __name__ == "__main__":
    migrate()
```

**Step 2: Update schema.sql**

Find the `CREATE TABLE om_events` block and add the two columns at the end (before the closing paren):

```sql
    ml_score          REAL,
    ml_risk_level     TEXT,
```

**Step 3: Update schema.postgres.sql**

Same columns in the PostgreSQL schema.

**Step 4: Run migration**

Run: `cd /Users/xa/Work_VC/va-signals-v2 && ./.venv/bin/python migrations/006_add_ml_score_columns.py`
Expected: `Migration 006: Added ml_score and ml_risk_level to om_events`

**Step 5: Commit**

```bash
cd /Users/xa/Work_VC/va-signals-v2
git add migrations/006_add_ml_score_columns.py schema.sql schema.postgres.sql
git commit -m "feat: add ml_score columns to om_events schema"
```

---

## Post-Sprint Verification

After all 6 tasks are complete, run the full verification:

```bash
cd /Users/xa/Work_VC/va-signals-v2

# 1. Full test suite
./.venv/bin/python -m pytest -v --tb=short

# 2. Verify ML routes are registered
./.venv/bin/python -c "from src.dashboard_api import app; paths = [r.path for r in app.routes]; assert '/api/ml/score' in paths; print('ML routes: OK')"

# 3. Verify CEO Brief target exists
make -n ceo-brief-dry

# 4. Verify parallelism
./.venv/bin/python -m pytest tests/oversight/test_runner.py::test_run_all_agents_parallelism -v
```

---

## What This Sprint Does NOT Include (Deferred to Sprint 2)

- Parallelize state runner (Sprint 2, Task 1)
- New signal schemas (Sprint 2, Task 2-4)
- Email health check (Sprint 2, Task 5)
- Dead-man's switch (Sprint 2, Task 6)
