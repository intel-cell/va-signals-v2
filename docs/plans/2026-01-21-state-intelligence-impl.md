# State Intelligence Module — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a state-level monitoring system for TX, CA, FL that tracks federal veteran program implementation signals with tiered alerting.

**Architecture:** Per-state modules with shared utilities. Source-first (official channels) + search-first (NewsAPI + RSS). Keyword classification for official sources, Haiku→Sonnet cascade for news.

**Tech Stack:** Python 3.12, SQLite, feedparser, httpx, BeautifulSoup, Anthropic Claude API, NewsAPI.org

---

## Phase 1: Schema & DB Helpers

### Task 1.1: Add State Intelligence Tables to Schema

**Files:**
- Modify: `schema.sql` (append to end)

**Step 1: Add the schema**

Append to `schema.sql`:

```sql
-- ============================================================================
-- STATE INTELLIGENCE TABLES
-- ============================================================================

-- Sources we monitor (official + news)
CREATE TABLE IF NOT EXISTS state_sources (
    source_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    source_type TEXT NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_state_sources_state ON state_sources(state);

-- Raw signals before classification
CREATE TABLE IF NOT EXISTS state_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT UNIQUE NOT NULL,
    state TEXT NOT NULL,
    source_id TEXT NOT NULL,
    program TEXT,
    title TEXT NOT NULL,
    content TEXT,
    url TEXT NOT NULL,
    pub_date TEXT,
    event_date TEXT,
    fetched_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES state_sources(source_id)
);

CREATE INDEX IF NOT EXISTS idx_state_signals_state ON state_signals(state);
CREATE INDEX IF NOT EXISTS idx_state_signals_pub_date ON state_signals(pub_date);

-- Classification results
CREATE TABLE IF NOT EXISTS state_classifications (
    signal_id TEXT PRIMARY KEY,
    severity TEXT NOT NULL,
    classification_method TEXT NOT NULL,
    keywords_matched TEXT,
    llm_reasoning TEXT,
    classified_at TEXT NOT NULL,
    FOREIGN KEY (signal_id) REFERENCES state_signals(signal_id)
);

CREATE INDEX IF NOT EXISTS idx_state_classifications_severity ON state_classifications(severity);

-- Track notification state
CREATE TABLE IF NOT EXISTS state_notifications (
    signal_id TEXT PRIMARY KEY,
    notified_at TEXT NOT NULL,
    channel TEXT NOT NULL,
    FOREIGN KEY (signal_id) REFERENCES state_signals(signal_id)
);

-- Run tracking
CREATE TABLE IF NOT EXISTS state_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,
    state TEXT,
    status TEXT NOT NULL,
    signals_found INTEGER DEFAULT 0,
    high_severity_count INTEGER DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_state_runs_status ON state_runs(status);

-- Source health tracking
CREATE TABLE IF NOT EXISTS state_source_health (
    source_id TEXT PRIMARY KEY,
    consecutive_failures INTEGER DEFAULT 0,
    last_success TEXT,
    last_failure TEXT,
    last_error TEXT,
    FOREIGN KEY (source_id) REFERENCES state_sources(source_id)
);
```

**Step 2: Verify schema applies**

Run:
```bash
rm -f /tmp/test_state_schema.db && sqlite3 /tmp/test_state_schema.db < schema.sql && echo "Schema OK"
```

Expected: "Schema OK"

**Step 3: Commit**

```bash
git add schema.sql
git commit -m "feat(state): add state intelligence tables to schema"
```

---

### Task 1.2: Create State DB Helpers Module

**Files:**
- Create: `src/state/__init__.py`
- Create: `src/state/db_helpers.py`
- Test: `tests/state/test_db_helpers.py`

**Step 1: Create module structure**

```bash
mkdir -p src/state tests/state
touch src/state/__init__.py tests/state/__init__.py
```

**Step 2: Write the failing test**

Create `tests/state/test_db_helpers.py`:

```python
"""Tests for state intelligence DB helpers."""

import pytest

from src.state.db_helpers import (
    insert_state_source,
    get_state_source,
    insert_state_signal,
    get_state_signal,
    signal_exists,
    insert_state_classification,
    get_state_classification,
    get_unnotified_signals,
    mark_signal_notified,
    start_state_run,
    finish_state_run,
    get_recent_state_runs,
    update_source_health,
    get_source_health,
    seed_default_sources,
)


def test_insert_and_get_state_source():
    source = {
        "source_id": "tx_tvc_news",
        "state": "TX",
        "source_type": "official",
        "name": "Texas Veterans Commission News",
        "url": "https://tvc.texas.gov/news",
    }

    insert_state_source(source)
    result = get_state_source("tx_tvc_news")

    assert result is not None
    assert result["state"] == "TX"
    assert result["source_type"] == "official"


def test_insert_and_get_state_signal():
    # First insert source
    source = {
        "source_id": "tx_tvc_news",
        "state": "TX",
        "source_type": "official",
        "name": "Texas Veterans Commission News",
        "url": "https://tvc.texas.gov/news",
    }
    insert_state_source(source)

    signal = {
        "signal_id": "sig-tx-001",
        "state": "TX",
        "source_id": "tx_tvc_news",
        "program": "pact_act",
        "title": "PACT Act Outreach Event",
        "content": "TVC announces new outreach...",
        "url": "https://tvc.texas.gov/news/pact-outreach",
        "pub_date": "2026-01-20",
        "fetched_at": "2026-01-21T10:00:00Z",
    }

    insert_state_signal(signal)
    result = get_state_signal("sig-tx-001")

    assert result is not None
    assert result["state"] == "TX"
    assert result["program"] == "pact_act"


def test_signal_exists():
    source = {
        "source_id": "tx_tvc_news",
        "state": "TX",
        "source_type": "official",
        "name": "TVC News",
        "url": "https://tvc.texas.gov/news",
    }
    insert_state_source(source)

    signal = {
        "signal_id": "sig-exists-001",
        "state": "TX",
        "source_id": "tx_tvc_news",
        "title": "Test Signal",
        "url": "https://example.com",
        "fetched_at": "2026-01-21T10:00:00Z",
    }
    insert_state_signal(signal)

    assert signal_exists("sig-exists-001") is True
    assert signal_exists("nonexistent") is False


def test_insert_and_get_classification():
    # Setup
    source = {
        "source_id": "tx_tvc_news",
        "state": "TX",
        "source_type": "official",
        "name": "TVC News",
        "url": "https://tvc.texas.gov/news",
    }
    insert_state_source(source)

    signal = {
        "signal_id": "sig-class-001",
        "state": "TX",
        "source_id": "tx_tvc_news",
        "title": "Budget Cut Announced",
        "url": "https://example.com",
        "fetched_at": "2026-01-21T10:00:00Z",
    }
    insert_state_signal(signal)

    classification = {
        "signal_id": "sig-class-001",
        "severity": "high",
        "classification_method": "keyword",
        "keywords_matched": '["budget cut"]',
    }
    insert_state_classification(classification)

    result = get_state_classification("sig-class-001")
    assert result is not None
    assert result["severity"] == "high"


def test_get_unnotified_signals():
    # Setup source and signals
    source = {
        "source_id": "tx_tvc_news",
        "state": "TX",
        "source_type": "official",
        "name": "TVC News",
        "url": "https://tvc.texas.gov/news",
    }
    insert_state_source(source)

    for i in range(3):
        signal = {
            "signal_id": f"sig-unnotified-{i}",
            "state": "TX",
            "source_id": "tx_tvc_news",
            "title": f"Signal {i}",
            "url": f"https://example.com/{i}",
            "fetched_at": "2026-01-21T10:00:00Z",
        }
        insert_state_signal(signal)

        classification = {
            "signal_id": f"sig-unnotified-{i}",
            "severity": "high" if i == 0 else "low",
            "classification_method": "keyword",
        }
        insert_state_classification(classification)

    # Get unnotified high-severity signals
    results = get_unnotified_signals(severity="high")
    assert len(results) >= 1
    assert all(r["severity"] == "high" for r in results)


def test_mark_signal_notified():
    # Setup
    source = {
        "source_id": "tx_tvc_news",
        "state": "TX",
        "source_type": "official",
        "name": "TVC News",
        "url": "https://tvc.texas.gov/news",
    }
    insert_state_source(source)

    signal = {
        "signal_id": "sig-notify-001",
        "state": "TX",
        "source_id": "tx_tvc_news",
        "title": "Test Signal",
        "url": "https://example.com",
        "fetched_at": "2026-01-21T10:00:00Z",
    }
    insert_state_signal(signal)

    classification = {
        "signal_id": "sig-notify-001",
        "severity": "high",
        "classification_method": "keyword",
    }
    insert_state_classification(classification)

    mark_signal_notified("sig-notify-001", "immediate")

    # Should no longer appear in unnotified
    results = get_unnotified_signals(severity="high")
    assert not any(r["signal_id"] == "sig-notify-001" for r in results)


def test_state_runs():
    run_id = start_state_run("morning", state="TX")
    assert run_id > 0

    finish_state_run(run_id, "SUCCESS", signals_found=5, high_severity_count=1)

    runs = get_recent_state_runs(limit=1)
    assert len(runs) == 1
    assert runs[0]["status"] == "SUCCESS"
    assert runs[0]["signals_found"] == 5


def test_source_health():
    source = {
        "source_id": "tx_health_test",
        "state": "TX",
        "source_type": "official",
        "name": "Health Test",
        "url": "https://example.com",
    }
    insert_state_source(source)

    # Record failures
    update_source_health("tx_health_test", success=False, error="Connection timeout")
    update_source_health("tx_health_test", success=False, error="Connection timeout")
    update_source_health("tx_health_test", success=False, error="Connection timeout")

    health = get_source_health("tx_health_test")
    assert health["consecutive_failures"] == 3

    # Record success resets counter
    update_source_health("tx_health_test", success=True)
    health = get_source_health("tx_health_test")
    assert health["consecutive_failures"] == 0


def test_seed_default_sources():
    seed_default_sources()

    # Check TX sources exist
    tx_tvc = get_state_source("tx_tvc_news")
    assert tx_tvc is not None
    assert tx_tvc["state"] == "TX"

    # Check CA sources exist
    ca_calvet = get_state_source("ca_calvet_news")
    assert ca_calvet is not None

    # Check FL sources exist
    fl_dva = get_state_source("fl_dva_news")
    assert fl_dva is not None
```

**Step 3: Run test to verify it fails**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_db_helpers.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.state.db_helpers'`

**Step 4: Write the implementation**

Create `src/state/__init__.py`:

```python
"""State Intelligence Module - monitors TX, CA, FL for federal veteran program signals."""
```

Create `src/state/db_helpers.py`:

```python
"""Database helpers for State Intelligence tables."""

import json
from datetime import datetime, timezone
from typing import Optional

from src.db import connect


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Source helpers ---


def insert_state_source(source: dict) -> None:
    """Insert a state source."""
    con = connect()
    con.execute(
        """
        INSERT OR IGNORE INTO state_sources (
            source_id, state, source_type, name, url, enabled, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source["source_id"],
            source["state"],
            source["source_type"],
            source["name"],
            source["url"],
            source.get("enabled", 1),
            _utc_now_iso(),
        ),
    )
    con.commit()


def get_state_source(source_id: str) -> Optional[dict]:
    """Get a state source by ID."""
    con = connect()
    cur = con.execute(
        "SELECT * FROM state_sources WHERE source_id = ?", (source_id,)
    )
    row = cur.fetchone()
    if not row:
        return None
    return dict(row)


def get_sources_by_state(state: str) -> list[dict]:
    """Get all enabled sources for a state."""
    con = connect()
    cur = con.execute(
        "SELECT * FROM state_sources WHERE state = ? AND enabled = 1",
        (state,),
    )
    return [dict(row) for row in cur.fetchall()]


# --- Signal helpers ---


def insert_state_signal(signal: dict) -> None:
    """Insert a state signal."""
    con = connect()
    con.execute(
        """
        INSERT OR IGNORE INTO state_signals (
            signal_id, state, source_id, program, title, content,
            url, pub_date, event_date, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal["signal_id"],
            signal["state"],
            signal["source_id"],
            signal.get("program"),
            signal["title"],
            signal.get("content"),
            signal["url"],
            signal.get("pub_date"),
            signal.get("event_date"),
            signal["fetched_at"],
        ),
    )
    con.commit()


def get_state_signal(signal_id: str) -> Optional[dict]:
    """Get a state signal by ID."""
    con = connect()
    cur = con.execute(
        "SELECT * FROM state_signals WHERE signal_id = ?", (signal_id,)
    )
    row = cur.fetchone()
    if not row:
        return None
    return dict(row)


def signal_exists(signal_id: str) -> bool:
    """Check if a signal already exists (for dedup)."""
    con = connect()
    cur = con.execute(
        "SELECT 1 FROM state_signals WHERE signal_id = ?", (signal_id,)
    )
    return cur.fetchone() is not None


def get_signals_by_state(
    state: str, since: Optional[str] = None, limit: int = 100
) -> list[dict]:
    """Get signals for a state, optionally since a date."""
    con = connect()
    if since:
        cur = con.execute(
            """
            SELECT * FROM state_signals
            WHERE state = ? AND fetched_at >= ?
            ORDER BY fetched_at DESC LIMIT ?
            """,
            (state, since, limit),
        )
    else:
        cur = con.execute(
            """
            SELECT * FROM state_signals
            WHERE state = ?
            ORDER BY fetched_at DESC LIMIT ?
            """,
            (state, limit),
        )
    return [dict(row) for row in cur.fetchall()]


# --- Classification helpers ---


def insert_state_classification(classification: dict) -> None:
    """Insert a classification result."""
    con = connect()
    con.execute(
        """
        INSERT OR REPLACE INTO state_classifications (
            signal_id, severity, classification_method,
            keywords_matched, llm_reasoning, classified_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            classification["signal_id"],
            classification["severity"],
            classification["classification_method"],
            classification.get("keywords_matched"),
            classification.get("llm_reasoning"),
            _utc_now_iso(),
        ),
    )
    con.commit()


def get_state_classification(signal_id: str) -> Optional[dict]:
    """Get classification for a signal."""
    con = connect()
    cur = con.execute(
        "SELECT * FROM state_classifications WHERE signal_id = ?",
        (signal_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return dict(row)


def get_unnotified_signals(
    severity: Optional[str] = None, limit: int = 100
) -> list[dict]:
    """Get signals that haven't been notified yet."""
    con = connect()
    query = """
        SELECT s.*, c.severity, c.classification_method, c.keywords_matched
        FROM state_signals s
        JOIN state_classifications c ON s.signal_id = c.signal_id
        LEFT JOIN state_notifications n ON s.signal_id = n.signal_id
        WHERE n.signal_id IS NULL
    """
    params = []

    if severity:
        query += " AND c.severity = ?"
        params.append(severity)

    query += " ORDER BY s.fetched_at DESC LIMIT ?"
    params.append(limit)

    cur = con.execute(query, params)
    return [dict(row) for row in cur.fetchall()]


def mark_signal_notified(signal_id: str, channel: str) -> None:
    """Mark a signal as notified."""
    con = connect()
    con.execute(
        """
        INSERT OR REPLACE INTO state_notifications (
            signal_id, notified_at, channel
        ) VALUES (?, ?, ?)
        """,
        (signal_id, _utc_now_iso(), channel),
    )
    con.commit()


# --- Run tracking ---


def start_state_run(run_type: str, state: Optional[str] = None) -> int:
    """Start a state run, return run ID."""
    con = connect()
    cur = con.execute(
        """
        INSERT INTO state_runs (run_type, state, status, started_at)
        VALUES (?, ?, 'RUNNING', ?)
        """,
        (run_type, state, _utc_now_iso()),
    )
    con.commit()
    return cur.lastrowid


def finish_state_run(
    run_id: int,
    status: str,
    signals_found: int = 0,
    high_severity_count: int = 0,
) -> None:
    """Finish a state run."""
    con = connect()
    con.execute(
        """
        UPDATE state_runs
        SET status = ?, signals_found = ?, high_severity_count = ?, finished_at = ?
        WHERE id = ?
        """,
        (status, signals_found, high_severity_count, _utc_now_iso(), run_id),
    )
    con.commit()


def get_recent_state_runs(limit: int = 10) -> list[dict]:
    """Get recent state runs."""
    con = connect()
    cur = con.execute(
        """
        SELECT * FROM state_runs
        ORDER BY started_at DESC LIMIT ?
        """,
        (limit,),
    )
    return [dict(row) for row in cur.fetchall()]


# --- Source health tracking ---


def update_source_health(
    source_id: str, success: bool, error: Optional[str] = None
) -> None:
    """Update source health tracking."""
    con = connect()
    now = _utc_now_iso()

    if success:
        con.execute(
            """
            INSERT INTO state_source_health (source_id, consecutive_failures, last_success)
            VALUES (?, 0, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                consecutive_failures = 0,
                last_success = ?
            """,
            (source_id, now, now),
        )
    else:
        con.execute(
            """
            INSERT INTO state_source_health (source_id, consecutive_failures, last_failure, last_error)
            VALUES (?, 1, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                consecutive_failures = consecutive_failures + 1,
                last_failure = ?,
                last_error = ?
            """,
            (source_id, now, error, now, error),
        )
    con.commit()


def get_source_health(source_id: str) -> Optional[dict]:
    """Get health status for a source."""
    con = connect()
    cur = con.execute(
        "SELECT * FROM state_source_health WHERE source_id = ?",
        (source_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return dict(row)


# --- Seeding ---


DEFAULT_SOURCES = [
    # Texas
    {
        "source_id": "tx_tvc_news",
        "state": "TX",
        "source_type": "official",
        "name": "Texas Veterans Commission News",
        "url": "https://tvc.texas.gov/news",
    },
    {
        "source_id": "tx_register",
        "state": "TX",
        "source_type": "official",
        "name": "Texas Register",
        "url": "https://texreg.sos.state.tx.us",
    },
    # California
    {
        "source_id": "ca_calvet_news",
        "state": "CA",
        "source_type": "official",
        "name": "CalVet Newsroom",
        "url": "https://calvet.ca.gov/news",
    },
    {
        "source_id": "ca_oal_register",
        "state": "CA",
        "source_type": "official",
        "name": "OAL Notice Register",
        "url": "https://oal.ca.gov/publications",
    },
    # Florida
    {
        "source_id": "fl_dva_news",
        "state": "FL",
        "source_type": "official",
        "name": "Florida DVA News",
        "url": "https://floridavets.org/news",
    },
    {
        "source_id": "fl_admin_register",
        "state": "FL",
        "source_type": "official",
        "name": "Florida Administrative Register",
        "url": "https://flrules.org",
    },
    # RSS Feeds
    {
        "source_id": "rss_texas_tribune",
        "state": "TX",
        "source_type": "rss",
        "name": "Texas Tribune",
        "url": "https://www.texastribune.org/feeds/rss/",
    },
    {
        "source_id": "rss_calmatters",
        "state": "CA",
        "source_type": "rss",
        "name": "CalMatters",
        "url": "https://calmatters.org/feed/",
    },
    {
        "source_id": "rss_florida_phoenix",
        "state": "FL",
        "source_type": "rss",
        "name": "Florida Phoenix",
        "url": "https://floridaphoenix.com/feed/",
    },
]


def seed_default_sources() -> int:
    """Seed default state sources. Returns count inserted."""
    count = 0
    for source in DEFAULT_SOURCES:
        if not get_state_source(source["source_id"]):
            insert_state_source(source)
            count += 1
    return count
```

**Step 5: Run tests to verify they pass**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_db_helpers.py -v
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/state/ tests/state/
git commit -m "feat(state): add state intelligence DB helpers"
```

---

## Phase 2: Common Utilities

### Task 2.1: Create Common Module with Keyword Matching and Dedup

**Files:**
- Create: `src/state/common.py`
- Test: `tests/state/test_common.py`

**Step 1: Write the failing test**

Create `tests/state/test_common.py`:

```python
"""Tests for state intelligence common utilities."""

import pytest

from src.state.common import (
    RawSignal,
    generate_signal_id,
    detect_program,
    VETERAN_KEYWORDS,
    is_veteran_relevant,
)


def test_raw_signal_creation():
    signal = RawSignal(
        url="https://example.com/news/1",
        title="PACT Act Outreach Event",
        content="Veterans are invited...",
        pub_date="2026-01-20",
        source_id="tx_tvc_news",
        state="TX",
    )

    assert signal.url == "https://example.com/news/1"
    assert signal.state == "TX"


def test_generate_signal_id():
    url = "https://tvc.texas.gov/news/pact-act-event"
    signal_id = generate_signal_id(url)

    assert signal_id is not None
    assert len(signal_id) == 64  # SHA-256 hex


def test_generate_signal_id_deterministic():
    url = "https://example.com/test"
    id1 = generate_signal_id(url)
    id2 = generate_signal_id(url)

    assert id1 == id2


def test_detect_program_pact_act():
    text = "Texas announces PACT Act toxic exposure screening initiative"
    program = detect_program(text)
    assert program == "pact_act"


def test_detect_program_community_care():
    text = "VA community care network adds new providers"
    program = detect_program(text)
    assert program == "community_care"


def test_detect_program_vha():
    text = "Veterans Health Administration facility coordination"
    program = detect_program(text)
    assert program == "vha"


def test_detect_program_none():
    text = "General veterans news about job fair"
    program = detect_program(text)
    assert program is None


def test_is_veteran_relevant_true():
    text = "Texas Veterans Commission announces new program"
    assert is_veteran_relevant(text) is True


def test_is_veteran_relevant_false():
    text = "Local bakery opens new location"
    assert is_veteran_relevant(text) is False


def test_is_veteran_relevant_va_mention():
    text = "VA healthcare expansion announced"
    assert is_veteran_relevant(text) is True
```

**Step 2: Run test to verify it fails**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_common.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `src/state/common.py`:

```python
"""Common utilities for State Intelligence module."""

import hashlib
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class RawSignal:
    """Raw signal from a state source."""

    url: str
    title: str
    source_id: str
    state: str
    content: Optional[str] = None
    pub_date: Optional[str] = None
    event_date: Optional[str] = None
    metadata: Optional[dict] = None


def generate_signal_id(url: str) -> str:
    """Generate deterministic signal ID from URL."""
    return hashlib.sha256(url.encode()).hexdigest()


# --- Program detection ---

PROGRAM_PATTERNS = {
    "pact_act": [
        r"pact act",
        r"toxic exposure",
        r"burn pit",
        r"presumptive condition",
    ],
    "community_care": [
        r"community care",
        r"choice program",
        r"mission act",
        r"provider network",
        r"ccn",  # Community Care Network
    ],
    "vha": [
        r"veterans health administration",
        r"vha",
        r"va hospital",
        r"va medical center",
        r"vamc",
        r"va facility",
    ],
}


def detect_program(text: str) -> Optional[str]:
    """Detect which federal program a signal relates to."""
    text_lower = text.lower()

    for program, patterns in PROGRAM_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return program

    return None


# --- Veteran relevance ---

VETERAN_KEYWORDS = [
    "veteran",
    "veterans",
    "va ",  # Space after to avoid false matches
    "v.a.",
    "military",
    "service member",
    "servicemember",
    "armed forces",
    "calvet",
    "tvc",  # Texas Veterans Commission
    "floridavets",
]


def is_veteran_relevant(text: str) -> bool:
    """Check if text is relevant to veterans."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in VETERAN_KEYWORDS)
```

**Step 4: Run tests to verify they pass**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_common.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/state/common.py tests/state/test_common.py
git commit -m "feat(state): add common utilities for signal processing"
```

---

## Phase 3: Classification

### Task 3.1: Create Keyword Classifier

**Files:**
- Create: `src/state/classify.py`
- Test: `tests/state/test_classify.py`

**Step 1: Write the failing test**

Create `tests/state/test_classify.py`:

```python
"""Tests for state intelligence classification."""

import pytest

from src.state.classify import (
    HIGH_SEVERITY_KEYWORDS,
    MEDIUM_SEVERITY_KEYWORDS,
    ClassificationResult,
    classify_by_keywords,
)


def test_classification_result_creation():
    result = ClassificationResult(
        severity="high",
        method="keyword",
        keywords_matched=["suspend"],
    )
    assert result.severity == "high"
    assert "suspend" in result.keywords_matched


def test_classify_high_severity_suspend():
    result = classify_by_keywords(
        title="Texas Veterans Commission suspends PACT Act program",
        content="The commission announced a suspension...",
    )
    assert result.severity == "high"
    assert "suspend" in result.keywords_matched


def test_classify_high_severity_backlog():
    result = classify_by_keywords(
        title="VA reports backlog in benefits claims",
        content="A significant backlog has developed...",
    )
    assert result.severity == "high"
    assert "backlog" in result.keywords_matched


def test_classify_high_severity_investigation():
    result = classify_by_keywords(
        title="Investigation launched into VA facility",
        content="State officials have launched an investigation...",
    )
    assert result.severity == "high"
    assert "investigation" in result.keywords_matched


def test_classify_medium_severity_resign():
    result = classify_by_keywords(
        title="CalVet Director to resign next month",
        content="The director announced plans to resign...",
    )
    assert result.severity == "medium"
    assert "resign" in result.keywords_matched


def test_classify_medium_severity_reform():
    result = classify_by_keywords(
        title="Florida announces VA healthcare reform",
        content="Major reforms are planned...",
    )
    assert result.severity == "medium"
    assert "reform" in result.keywords_matched


def test_classify_low_severity_routine():
    result = classify_by_keywords(
        title="Veterans Day ceremony held at state capitol",
        content="State officials gathered to honor veterans...",
    )
    assert result.severity == "low"
    assert len(result.keywords_matched) == 0


def test_classify_multiple_keywords():
    result = classify_by_keywords(
        title="Investigation reveals budget cut failures",
        content="The investigation found budget cuts led to failures...",
    )
    assert result.severity == "high"
    # Should match multiple high-severity keywords
    assert len(result.keywords_matched) >= 2
```

**Step 2: Run test to verify it fails**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_classify.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `src/state/classify.py`:

```python
"""Classification for state intelligence signals."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ClassificationResult:
    """Result of signal classification."""

    severity: str  # "high", "medium", "low", "noise"
    method: str  # "keyword", "llm"
    keywords_matched: list[str] = field(default_factory=list)
    llm_reasoning: Optional[str] = None


HIGH_SEVERITY_KEYWORDS = [
    # Program disruptions
    "suspend",
    "terminate",
    "cancel",
    "halt",
    "pause",
    "defund",
    "eliminate",
    "discontinue",
    # Problems
    "backlog",
    "delay",
    "shortage",
    "crisis",
    "failure",
    "investigation",
    "audit finding",
    "misconduct",
    # Cuts
    "budget cut",
    "funding cut",
    "layoff",
    "closure",
]

MEDIUM_SEVERITY_KEYWORDS = [
    # Leadership changes
    "resign",
    "retire",
    "appoint",
    "nomination",
    # Policy shifts
    "overhaul",
    "reform",
    "restructure",
    "review",
    # Access issues
    "wait time",
    "access",
    "capacity",
]


def classify_by_keywords(
    title: str, content: Optional[str] = None
) -> ClassificationResult:
    """
    Classify signal severity by keyword matching.

    Used for official sources where content is structured.
    """
    text = f"{title} {content or ''}".lower()

    # Check high-severity keywords
    high_matches = [kw for kw in HIGH_SEVERITY_KEYWORDS if kw in text]
    if high_matches:
        return ClassificationResult(
            severity="high",
            method="keyword",
            keywords_matched=high_matches,
        )

    # Check medium-severity keywords
    medium_matches = [kw for kw in MEDIUM_SEVERITY_KEYWORDS if kw in text]
    if medium_matches:
        return ClassificationResult(
            severity="medium",
            method="keyword",
            keywords_matched=medium_matches,
        )

    # Default to low
    return ClassificationResult(
        severity="low",
        method="keyword",
        keywords_matched=[],
    )
```

**Step 4: Run tests to verify they pass**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_classify.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/state/classify.py tests/state/test_classify.py
git commit -m "feat(state): add keyword-based severity classification"
```

---

### Task 3.2: Add LLM Classifier for News Sources

**Files:**
- Modify: `src/state/classify.py`
- Modify: `tests/state/test_classify.py`

**Step 1: Add tests for LLM classifier**

Append to `tests/state/test_classify.py`:

```python
from unittest.mock import patch, MagicMock


def test_classify_by_llm_high_severity():
    mock_response = {
        "is_specific_event": True,
        "federal_program": "pact_act",
        "severity": "high",
        "reasoning": "Reports suspension of PACT Act program",
    }

    with patch("src.state.classify._call_haiku") as mock_haiku:
        mock_haiku.return_value = mock_response

        from src.state.classify import classify_by_llm

        result = classify_by_llm(
            title="Texas suspends PACT Act outreach",
            content="The state has suspended...",
            state="TX",
        )

        assert result.severity == "high"
        assert result.method == "llm"
        assert "suspension" in result.llm_reasoning.lower() or mock_response["reasoning"] in (result.llm_reasoning or "")


def test_classify_by_llm_filters_noise():
    mock_response = {
        "is_specific_event": False,
        "federal_program": None,
        "severity": "noise",
        "reasoning": "General explainer article, no specific event",
    }

    with patch("src.state.classify._call_haiku") as mock_haiku:
        mock_haiku.return_value = mock_response

        from src.state.classify import classify_by_llm

        result = classify_by_llm(
            title="How to apply for VA benefits",
            content="Veterans can apply by...",
            state="TX",
        )

        assert result.severity == "noise"


def test_classify_by_llm_fallback_on_error():
    with patch("src.state.classify._call_haiku") as mock_haiku:
        mock_haiku.side_effect = Exception("API error")

        from src.state.classify import classify_by_llm

        result = classify_by_llm(
            title="Important veteran news",
            content="Something happened...",
            state="TX",
        )

        # Should fall back to keyword classification
        assert result.method == "keyword"
```

**Step 2: Run test to verify it fails**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_classify.py::test_classify_by_llm_high_severity -v
```

Expected: FAIL with `cannot import name 'classify_by_llm'`

**Step 3: Add LLM classifier to implementation**

Append to `src/state/classify.py`:

```python
import json
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

HAIKU_PROMPT = """Analyze this news article about veterans in {state}.

Title: {title}
Content: {content}

Questions:
1. Does this report a SPECIFIC, DATED event (not a general explainer)?
2. Does it indicate a problem with federal program implementation (PACT Act, Community Care, VHA)?
3. Severity: Is this a disruption/failure (HIGH), policy shift (MEDIUM), or routine/positive news (LOW)?

Respond as JSON only:
{{"is_specific_event": bool, "federal_program": str|null, "severity": "high"|"medium"|"low"|"noise", "reasoning": str}}"""


def _get_api_key() -> str:
    """Get Anthropic API key from Keychain."""
    result = subprocess.run(
        ["security", "find-generic-password", "-s", "claude-api", "-w"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError("Could not retrieve claude-api key from Keychain")
    return result.stdout.strip()


def _call_haiku(prompt: str) -> dict:
    """Call Haiku model and return parsed JSON response."""
    import anthropic

    client = anthropic.Anthropic(api_key=_get_api_key())

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract text and parse JSON
    text = response.content[0].text
    # Find JSON in response
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])
    raise ValueError(f"Could not parse JSON from response: {text}")


def classify_by_llm(
    title: str,
    content: Optional[str],
    state: str,
) -> ClassificationResult:
    """
    Classify signal using LLM (Haiku).

    Used for news sources where content is unstructured.
    Falls back to keyword classification on error.
    """
    try:
        prompt = HAIKU_PROMPT.format(
            state=state,
            title=title,
            content=content or "(no content)",
        )

        result = _call_haiku(prompt)

        # Filter out noise (non-events, explainers)
        if not result.get("is_specific_event") or result.get("severity") == "noise":
            return ClassificationResult(
                severity="noise",
                method="llm",
                llm_reasoning=result.get("reasoning"),
            )

        return ClassificationResult(
            severity=result["severity"],
            method="llm",
            llm_reasoning=result.get("reasoning"),
        )

    except Exception as e:
        logger.warning(f"LLM classification failed, falling back to keywords: {e}")
        return classify_by_keywords(title, content)
```

**Step 4: Run tests to verify they pass**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_classify.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/state/classify.py tests/state/test_classify.py
git commit -m "feat(state): add LLM-based classification with Haiku"
```

---

## Phase 4: Official Sources

### Task 4.1: Create Base Source Class

**Files:**
- Create: `src/state/sources/__init__.py`
- Create: `src/state/sources/base.py`
- Test: `tests/state/test_sources/__init__.py`
- Test: `tests/state/test_sources/test_base.py`

**Step 1: Create directories**

```bash
mkdir -p src/state/sources tests/state/test_sources
touch src/state/sources/__init__.py tests/state/test_sources/__init__.py
```

**Step 2: Write the failing test**

Create `tests/state/test_sources/test_base.py`:

```python
"""Tests for base source class."""

import pytest
from abc import ABC

from src.state.sources.base import StateSource
from src.state.common import RawSignal


def test_state_source_is_abstract():
    """StateSource should be abstract and not instantiable."""
    with pytest.raises(TypeError):
        StateSource()


def test_state_source_subclass():
    """Subclass must implement fetch method."""

    class TestSource(StateSource):
        source_id = "test_source"
        state = "TX"

        def fetch(self):
            return [
                RawSignal(
                    url="https://example.com/1",
                    title="Test Signal",
                    source_id=self.source_id,
                    state=self.state,
                )
            ]

    source = TestSource()
    signals = source.fetch()

    assert len(signals) == 1
    assert signals[0].state == "TX"
```

**Step 3: Run test to verify it fails**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_sources/test_base.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 4: Write the implementation**

Create `src/state/sources/base.py`:

```python
"""Base class for state intelligence sources."""

from abc import ABC, abstractmethod
from typing import Optional

from src.state.common import RawSignal


class StateSource(ABC):
    """Abstract base class for state sources."""

    source_id: str
    state: str

    @abstractmethod
    def fetch(self) -> list[RawSignal]:
        """Fetch signals from this source."""
        pass
```

Update `src/state/sources/__init__.py`:

```python
"""State intelligence sources."""

from .base import StateSource

__all__ = ["StateSource"]
```

**Step 5: Run tests to verify they pass**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_sources/test_base.py -v
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/state/sources/ tests/state/test_sources/
git commit -m "feat(state): add base source class"
```

---

### Task 4.2: Implement Texas Official Source

**Files:**
- Create: `src/state/sources/tx_official.py`
- Test: `tests/state/test_sources/test_tx_official.py`
- Fixture: `tests/state/fixtures/tvc_news.html`

**Step 1: Create fixtures directory**

```bash
mkdir -p tests/state/fixtures
```

**Step 2: Create test fixture**

Create `tests/state/fixtures/tvc_news.html`:

```html
<!DOCTYPE html>
<html>
<head><title>TVC News</title></head>
<body>
<div class="news-list">
  <article class="news-item">
    <h2><a href="/news/pact-act-outreach">PACT Act Outreach Event Announced</a></h2>
    <time datetime="2026-01-20">January 20, 2026</time>
    <p>The Texas Veterans Commission announces a new PACT Act outreach event...</p>
  </article>
  <article class="news-item">
    <h2><a href="/news/budget-update">TVC Budget Update</a></h2>
    <time datetime="2026-01-18">January 18, 2026</time>
    <p>Quarterly budget review shows funding concerns...</p>
  </article>
</div>
</body>
</html>
```

**Step 3: Write the failing test**

Create `tests/state/test_sources/test_tx_official.py`:

```python
"""Tests for Texas official sources."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.state.sources.tx_official import TXOfficialSource
from src.state.common import RawSignal


@pytest.fixture
def tvc_html():
    fixture_path = Path(__file__).parent.parent / "fixtures" / "tvc_news.html"
    return fixture_path.read_text()


def test_tx_source_attributes():
    source = TXOfficialSource()
    assert source.source_id == "tx_tvc_news"
    assert source.state == "TX"


def test_tx_source_parse_tvc_news(tvc_html):
    source = TXOfficialSource()

    with patch("src.state.sources.tx_official.httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = tvc_html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        signals = source.fetch()

    assert len(signals) >= 2
    assert any("PACT Act" in s.title for s in signals)


def test_tx_source_extracts_dates(tvc_html):
    source = TXOfficialSource()

    with patch("src.state.sources.tx_official.httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = tvc_html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        signals = source.fetch()

    # Should extract pub_date
    pact_signal = next((s for s in signals if "PACT" in s.title), None)
    assert pact_signal is not None
    assert pact_signal.pub_date == "2026-01-20"


def test_tx_source_handles_error():
    source = TXOfficialSource()

    with patch("src.state.sources.tx_official.httpx.get") as mock_get:
        mock_get.side_effect = Exception("Connection error")

        signals = source.fetch()

    # Should return empty list on error, not raise
    assert signals == []
```

**Step 4: Run test to verify it fails**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_sources/test_tx_official.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 5: Write the implementation**

Create `src/state/sources/tx_official.py`:

```python
"""Texas official sources - TVC News and Texas Register."""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

TVC_NEWS_URL = "https://tvc.texas.gov/news"


class TXOfficialSource(StateSource):
    """Fetches from Texas Veterans Commission and Texas Register."""

    source_id = "tx_tvc_news"
    state = "TX"

    def __init__(self, base_url: str = TVC_NEWS_URL):
        self.base_url = base_url

    def fetch(self) -> list[RawSignal]:
        """Fetch news from TVC website."""
        try:
            response = httpx.get(self.base_url, timeout=30.0)
            response.raise_for_status()
            return self._parse_tvc_news(response.text)
        except Exception as e:
            logger.error(f"Failed to fetch TVC news: {e}")
            return []

    def _parse_tvc_news(self, html: str) -> list[RawSignal]:
        """Parse TVC news page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        signals = []

        # Find news items - adjust selectors based on actual site structure
        for article in soup.select("article.news-item, .news-item, article"):
            try:
                # Extract title and link
                title_elem = article.select_one("h2 a, h3 a, .title a")
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                href = title_elem.get("href", "")

                # Build full URL
                if href.startswith("/"):
                    url = f"https://tvc.texas.gov{href}"
                elif href.startswith("http"):
                    url = href
                else:
                    url = f"{self.base_url}/{href}"

                # Extract date
                date_elem = article.select_one("time, .date, .pub-date")
                pub_date = None
                if date_elem:
                    datetime_attr = date_elem.get("datetime")
                    if datetime_attr:
                        pub_date = datetime_attr[:10]  # YYYY-MM-DD
                    else:
                        # Try to parse text
                        pub_date = self._parse_date_text(date_elem.get_text())

                # Extract excerpt
                excerpt_elem = article.select_one("p, .excerpt, .summary")
                content = excerpt_elem.get_text(strip=True) if excerpt_elem else None

                signals.append(
                    RawSignal(
                        url=url,
                        title=title,
                        content=content,
                        pub_date=pub_date,
                        source_id=self.source_id,
                        state=self.state,
                    )
                )

            except Exception as e:
                logger.warning(f"Failed to parse article: {e}")
                continue

        return signals

    def _parse_date_text(self, text: str) -> Optional[str]:
        """Try to parse date from text like 'January 20, 2026'."""
        try:
            # Common date formats
            for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"]:
                try:
                    dt = datetime.strptime(text.strip(), fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            return None
        except Exception:
            return None
```

**Step 6: Run tests to verify they pass**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_sources/test_tx_official.py -v
```

Expected: All tests PASS

**Step 7: Commit**

```bash
git add src/state/sources/tx_official.py tests/state/test_sources/test_tx_official.py tests/state/fixtures/
git commit -m "feat(state): add Texas official source (TVC News)"
```

---

### Task 4.3: Implement California Official Source

**Files:**
- Create: `src/state/sources/ca_official.py`
- Test: `tests/state/test_sources/test_ca_official.py`
- Fixture: `tests/state/fixtures/calvet_news.html`

**Step 1: Create test fixture**

Create `tests/state/fixtures/calvet_news.html`:

```html
<!DOCTYPE html>
<html>
<head><title>CalVet News</title></head>
<body>
<div class="news-container">
  <div class="news-article">
    <h3><a href="/news/2026/01/pact-screening">CalVet Expands PACT Act Screening</a></h3>
    <span class="date">01/19/2026</span>
    <p>CalVet announces expanded toxic exposure screening locations...</p>
  </div>
  <div class="news-article">
    <h3><a href="/news/2026/01/community-care">Community Care Provider Update</a></h3>
    <span class="date">01/17/2026</span>
    <p>New providers added to California VA community care network...</p>
  </div>
</div>
</body>
</html>
```

**Step 2: Write the failing test**

Create `tests/state/test_sources/test_ca_official.py`:

```python
"""Tests for California official sources."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.state.sources.ca_official import CAOfficialSource


@pytest.fixture
def calvet_html():
    fixture_path = Path(__file__).parent.parent / "fixtures" / "calvet_news.html"
    return fixture_path.read_text()


def test_ca_source_attributes():
    source = CAOfficialSource()
    assert source.source_id == "ca_calvet_news"
    assert source.state == "CA"


def test_ca_source_parse_calvet_news(calvet_html):
    source = CAOfficialSource()

    with patch("src.state.sources.ca_official.httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = calvet_html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        signals = source.fetch()

    assert len(signals) >= 2
    assert any("PACT" in s.title for s in signals)


def test_ca_source_handles_error():
    source = CAOfficialSource()

    with patch("src.state.sources.ca_official.httpx.get") as mock_get:
        mock_get.side_effect = Exception("Connection error")

        signals = source.fetch()

    assert signals == []
```

**Step 3: Run test to verify it fails**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_sources/test_ca_official.py -v
```

Expected: FAIL

**Step 4: Write the implementation**

Create `src/state/sources/ca_official.py`:

```python
"""California official sources - CalVet Newsroom."""

import logging
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

CALVET_NEWS_URL = "https://calvet.ca.gov/news"


class CAOfficialSource(StateSource):
    """Fetches from CalVet Newsroom."""

    source_id = "ca_calvet_news"
    state = "CA"

    def __init__(self, base_url: str = CALVET_NEWS_URL):
        self.base_url = base_url

    def fetch(self) -> list[RawSignal]:
        """Fetch news from CalVet website."""
        try:
            response = httpx.get(self.base_url, timeout=30.0)
            response.raise_for_status()
            return self._parse_calvet_news(response.text)
        except Exception as e:
            logger.error(f"Failed to fetch CalVet news: {e}")
            return []

    def _parse_calvet_news(self, html: str) -> list[RawSignal]:
        """Parse CalVet news page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        signals = []

        for article in soup.select(".news-article, article, .post"):
            try:
                title_elem = article.select_one("h3 a, h2 a, .title a")
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                href = title_elem.get("href", "")

                if href.startswith("/"):
                    url = f"https://calvet.ca.gov{href}"
                elif href.startswith("http"):
                    url = href
                else:
                    url = f"{self.base_url}/{href}"

                date_elem = article.select_one(".date, time, .pub-date")
                pub_date = None
                if date_elem:
                    pub_date = self._parse_date_text(date_elem.get_text())

                excerpt_elem = article.select_one("p, .excerpt")
                content = excerpt_elem.get_text(strip=True) if excerpt_elem else None

                signals.append(
                    RawSignal(
                        url=url,
                        title=title,
                        content=content,
                        pub_date=pub_date,
                        source_id=self.source_id,
                        state=self.state,
                    )
                )

            except Exception as e:
                logger.warning(f"Failed to parse CalVet article: {e}")
                continue

        return signals

    def _parse_date_text(self, text: str) -> Optional[str]:
        """Parse date from various formats."""
        text = text.strip()
        for fmt in ["%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(text, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
```

**Step 5: Run tests to verify they pass**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_sources/test_ca_official.py -v
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/state/sources/ca_official.py tests/state/test_sources/test_ca_official.py tests/state/fixtures/calvet_news.html
git commit -m "feat(state): add California official source (CalVet News)"
```

---

### Task 4.4: Implement Florida Official Source

**Files:**
- Create: `src/state/sources/fl_official.py`
- Test: `tests/state/test_sources/test_fl_official.py`
- Fixture: `tests/state/fixtures/fl_dva_news.html`

**Step 1: Create test fixture**

Create `tests/state/fixtures/fl_dva_news.html`:

```html
<!DOCTYPE html>
<html>
<head><title>Florida DVA News</title></head>
<body>
<div class="news-feed">
  <div class="news-entry">
    <a href="/newsroom/pact-act-florida" class="news-title">Florida Expands PACT Act Services</a>
    <div class="news-date">January 18, 2026</div>
    <div class="news-summary">Florida DVA announces expanded services for toxic exposure veterans...</div>
  </div>
  <div class="news-entry">
    <a href="/newsroom/va-partnership" class="news-title">VA Healthcare Partnership Announced</a>
    <div class="news-date">January 15, 2026</div>
    <div class="news-summary">New partnership with VA facilities across Florida...</div>
  </div>
</div>
</body>
</html>
```

**Step 2: Write the failing test**

Create `tests/state/test_sources/test_fl_official.py`:

```python
"""Tests for Florida official sources."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.state.sources.fl_official import FLOfficialSource


@pytest.fixture
def fl_dva_html():
    fixture_path = Path(__file__).parent.parent / "fixtures" / "fl_dva_news.html"
    return fixture_path.read_text()


def test_fl_source_attributes():
    source = FLOfficialSource()
    assert source.source_id == "fl_dva_news"
    assert source.state == "FL"


def test_fl_source_parse_dva_news(fl_dva_html):
    source = FLOfficialSource()

    with patch("src.state.sources.fl_official.httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = fl_dva_html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        signals = source.fetch()

    assert len(signals) >= 2
    assert any("PACT" in s.title for s in signals)


def test_fl_source_handles_error():
    source = FLOfficialSource()

    with patch("src.state.sources.fl_official.httpx.get") as mock_get:
        mock_get.side_effect = Exception("Connection error")

        signals = source.fetch()

    assert signals == []
```

**Step 3: Run test to verify it fails**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_sources/test_fl_official.py -v
```

Expected: FAIL

**Step 4: Write the implementation**

Create `src/state/sources/fl_official.py`:

```python
"""Florida official sources - Florida DVA News."""

import logging
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from src.state.common import RawSignal
from src.state.sources.base import StateSource

logger = logging.getLogger(__name__)

FL_DVA_NEWS_URL = "https://floridavets.org/news"


class FLOfficialSource(StateSource):
    """Fetches from Florida Department of Veterans Affairs."""

    source_id = "fl_dva_news"
    state = "FL"

    def __init__(self, base_url: str = FL_DVA_NEWS_URL):
        self.base_url = base_url

    def fetch(self) -> list[RawSignal]:
        """Fetch news from Florida DVA website."""
        try:
            response = httpx.get(self.base_url, timeout=30.0)
            response.raise_for_status()
            return self._parse_fl_news(response.text)
        except Exception as e:
            logger.error(f"Failed to fetch Florida DVA news: {e}")
            return []

    def _parse_fl_news(self, html: str) -> list[RawSignal]:
        """Parse Florida DVA news page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        signals = []

        for entry in soup.select(".news-entry, .news-item, article"):
            try:
                title_elem = entry.select_one(".news-title, h2 a, h3 a, a.title")
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                href = title_elem.get("href", "")

                if href.startswith("/"):
                    url = f"https://floridavets.org{href}"
                elif href.startswith("http"):
                    url = href
                else:
                    url = f"{self.base_url}/{href}"

                date_elem = entry.select_one(".news-date, .date, time")
                pub_date = None
                if date_elem:
                    pub_date = self._parse_date_text(date_elem.get_text())

                summary_elem = entry.select_one(".news-summary, .summary, p")
                content = summary_elem.get_text(strip=True) if summary_elem else None

                signals.append(
                    RawSignal(
                        url=url,
                        title=title,
                        content=content,
                        pub_date=pub_date,
                        source_id=self.source_id,
                        state=self.state,
                    )
                )

            except Exception as e:
                logger.warning(f"Failed to parse FL DVA article: {e}")
                continue

        return signals

    def _parse_date_text(self, text: str) -> Optional[str]:
        """Parse date from various formats."""
        text = text.strip()
        for fmt in ["%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(text, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
```

**Step 5: Run tests to verify they pass**

Run:
```bash
./.venv/bin/python -m pytest tests/state/test_sources/test_fl_official.py -v
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/state/sources/fl_official.py tests/state/test_sources/test_fl_official.py tests/state/fixtures/fl_dva_news.html
git commit -m "feat(state): add Florida official source (DVA News)"
```

---

## Remaining Phases (Summary)

The following phases follow the same TDD pattern:

### Phase 5: News Sources
- Task 5.1: NewsAPI client with search queries
- Task 5.2: RSS aggregator for local news
- Task 5.3: Dedup across sources

### Phase 6: Runner
- Task 6.1: Main orchestrator (`src/state/runner.py`)
- Task 6.2: State-by-state execution
- Task 6.3: Error handling and health tracking

### Phase 7: Output Formatters
- Task 7.1: Slack immediate alert formatter
- Task 7.2: Weekly digest generator
- Task 7.3: Integration with existing `src/reports.py`

### Phase 8: Dashboard Integration
- Task 8.1: Add `/api/state/signals` endpoint
- Task 8.2: Add `/api/state/stats` endpoint
- Task 8.3: Update dashboard UI

### Phase 9: Makefile & CLI
- Task 9.1: Add `make state-monitor` command
- Task 9.2: Add `--run-type morning|evening` flag
- Task 9.3: Add `--backfill` mode

---

## Verification Checklist

After completing all phases:

- [ ] `make test` passes (all existing + new tests)
- [ ] `make state-monitor` runs without error
- [ ] Official sources (TX, CA, FL) fetch and parse correctly
- [ ] NewsAPI integration works with API key
- [ ] High-severity signals trigger Slack alerts
- [ ] Weekly digest includes state signals grouped by state/program
- [ ] Dashboard shows state intelligence tab
- [ ] Source health tracking works (3 failures → alert)
