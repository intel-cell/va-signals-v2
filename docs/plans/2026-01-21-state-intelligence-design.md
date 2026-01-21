# State Intelligence Module - Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Monitor Texas, California, and Florida for federal veteran program implementation signals, with tiered alerting.

**Architecture:** Per-state modules with shared utilities. Source-first (official channels) + search-first (news APIs) approaches. Keyword classification for official sources, LLM cascade for news.

**Tech Stack:** Python, NewsAPI.org, RSS/feedparser, Haiku/Sonnet for classification, SQLite, existing Slack/email infrastructure.

---

## 1. Scope

### States (Top 3 by Veteran Population)

| Rank | State | Veteran Pop | Coverage |
|------|-------|-------------|----------|
| 1 | Texas | 1.5M | 8.4% |
| 2 | California | 1.4M | 7.8% |
| 3 | Florida | 1.4M | 7.7% |

Combined: ~24% of US veterans.

### Federal Programs (Health-Focused)

Priority order based on state-level implementation variance and veteran impact:

1. **PACT Act** - Outreach grants, toxic exposure screening, enrollment drives
2. **Community Care** - Provider network adequacy, referral processes, wait times
3. **VHA** - State-VA facility coordination, emergency care agreements

### Priority Categories

1. State implementation of federal programs (highest)
2. State regulatory actions
3. State legislation affecting veterans
4. State veteran benefits programs (lowest)

---

## 2. Architecture

### Module Structure

```
src/state/
├── __init__.py
├── common.py              # Shared utilities
├── sources/
│   ├── __init__.py
│   ├── newsapi.py         # NewsAPI.org client
│   ├── rss.py             # RSS aggregator
│   ├── tx_official.py     # Texas Veterans Commission, Texas Register
│   ├── ca_official.py     # CalVet, OAL Notice Register
│   └── fl_official.py     # Florida DVA, FL Admin Register
├── classify.py            # Severity classification (keywords + LLM)
├── db_helpers.py          # State-specific DB operations
└── runner.py              # Orchestrates twice-daily runs
```

### Data Flow

```
Official Sources (TX/CA/FL) ──→ Keyword Classification ──→ state_signals table
                                        │
News Sources (NewsAPI + RSS) ──→ LLM Classification ───→ state_signals table
                                        │
                                        ↓
                            ┌───────────────────┐
                            │ Severity Router   │
                            └───────────────────┘
                                   │    │
                    High-severity ─┘    └─ Routine
                          │                   │
                          ↓                   ↓
                    Immediate Slack     Weekly Digest
```

---

## 3. Database Schema

```sql
-- Sources we monitor (official + news)
CREATE TABLE IF NOT EXISTS state_sources (
    source_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,              -- 'TX', 'CA', 'FL'
    source_type TEXT NOT NULL,        -- 'official', 'news', 'rss'
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

-- Raw signals before classification
CREATE TABLE IF NOT EXISTS state_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT UNIQUE NOT NULL,   -- Dedup key (URL hash or unique ID)
    state TEXT NOT NULL,
    source_id TEXT NOT NULL,
    program TEXT,                      -- 'pact_act', 'community_care', 'vha', NULL
    title TEXT NOT NULL,
    content TEXT,
    url TEXT NOT NULL,
    pub_date TEXT,                     -- Source publication date
    event_date TEXT,                   -- Actual event date if different
    fetched_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES state_sources(source_id)
);

-- Classification results
CREATE TABLE IF NOT EXISTS state_classifications (
    signal_id TEXT PRIMARY KEY,
    severity TEXT NOT NULL,            -- 'high', 'medium', 'low', 'noise'
    classification_method TEXT NOT NULL, -- 'keyword', 'llm'
    keywords_matched TEXT,             -- JSON array if keyword match
    llm_reasoning TEXT,                -- LLM explanation if used
    classified_at TEXT NOT NULL,
    FOREIGN KEY (signal_id) REFERENCES state_signals(signal_id)
);

-- Track notification state
CREATE TABLE IF NOT EXISTS state_notifications (
    signal_id TEXT PRIMARY KEY,
    notified_at TEXT NOT NULL,
    channel TEXT NOT NULL,             -- 'immediate', 'weekly_digest'
    FOREIGN KEY (signal_id) REFERENCES state_signals(signal_id)
);

-- Run tracking (matches existing source_runs pattern)
CREATE TABLE IF NOT EXISTS state_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,            -- 'morning', 'evening'
    state TEXT,                        -- NULL for all-state runs
    status TEXT NOT NULL,              -- 'SUCCESS', 'NO_DATA', 'ERROR'
    signals_found INTEGER DEFAULT 0,
    high_severity_count INTEGER DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
```

---

## 4. Official Sources (Source-First)

### Texas

| Source | URL | Format | Cadence |
|--------|-----|--------|---------|
| TX Veterans Commission News | tvc.texas.gov/news | HTML scrape | Twice daily |
| Texas Register | texreg.sos.state.tx.us | Weekly PDF | Weekly check |

### California

| Source | URL | Format | Cadence |
|--------|-----|--------|---------|
| CalVet Newsroom | calvet.ca.gov/news | HTML/RSS | Twice daily |
| OAL Notice Register | oal.ca.gov/publications | Structured HTML | Weekly check |

### Florida

| Source | URL | Format | Cadence |
|--------|-----|--------|---------|
| FL Dept of Veterans Affairs | floridavets.org/news | HTML scrape | Twice daily |
| FL Administrative Register | flrules.org | HTML | Weekly check |

### Module Pattern

```python
# src/state/sources/tx_official.py

class TXOfficialSource:
    """Fetches from Texas Veterans Commission and Texas Register."""

    def fetch_tvc_news(self) -> list[RawSignal]:
        """Scrape TVC news page for announcements."""

    def fetch_texas_register(self) -> list[RawSignal]:
        """Check Texas Register for veteran-related rules."""

    def fetch_all(self) -> list[RawSignal]:
        """Fetch from all TX official sources."""
```

---

## 5. News Sources (Search-First)

### NewsAPI.org

Primary news source. 100 requests/day free tier sufficient for 3 states x 3 programs.

```python
SEARCH_QUERIES = {
    "TX": [
        "Texas veterans PACT Act",
        "Texas VA community care",
        "Texas Veterans Commission",
    ],
    "CA": [
        "California veterans PACT Act",
        "CalVet toxic exposure",
        "California VA community care",
    ],
    "FL": [
        "Florida veterans PACT Act",
        "Florida VA healthcare",
        "Florida veterans affairs",
    ],
}
```

API key stored in macOS Keychain as `newsapi-key`.

### Curated RSS Feeds

Supplementary local coverage:

| State | Outlet | Why |
|-------|--------|-----|
| TX | Texas Tribune | Nonprofit, deep state gov coverage |
| TX | Houston Chronicle | Large veteran population in Houston area |
| CA | CalMatters | Nonprofit, state policy focused |
| CA | LA Times | Covers CalVet regularly |
| FL | Florida Phoenix | State gov focused |
| FL | Tampa Bay Times | Strong investigative, large vet community |

### Swappable Interface

```python
class NewsSource(Protocol):
    def search(self, query: str, state: str) -> list[NewsItem]: ...

class NewsAPISource(NewsSource): ...
class RSSAggregatorSource(NewsSource): ...
```

---

## 6. Severity Classification

### Keywords (Official Sources)

```python
HIGH_SEVERITY_KEYWORDS = [
    # Program disruptions
    "suspend", "terminate", "cancel", "halt", "pause",
    "defund", "eliminate", "discontinue",
    # Problems
    "backlog", "delay", "shortage", "crisis", "failure",
    "investigation", "audit finding", "misconduct",
    # Cuts
    "budget cut", "funding cut", "layoff", "closure",
]

MEDIUM_SEVERITY_KEYWORDS = [
    # Leadership changes
    "resign", "retire", "appoint", "nomination",
    # Policy shifts
    "overhaul", "reform", "restructure", "review",
    # Access issues
    "wait time", "access", "capacity",
]
```

### LLM Cascade (News Sources)

**Stage 1: Haiku pre-filter**

```
Analyze this news article about veterans in {state}.

Title: {title}
Content: {content}

Questions:
1. Does this report a SPECIFIC, DATED event (not a general explainer)?
2. Does it indicate a problem with federal program implementation?
3. Severity: disruption/failure (HIGH), policy shift (MEDIUM), routine (LOW)?

Respond as JSON:
{"is_specific_event": bool, "federal_program": str|null, "severity": "high"|"medium"|"low"|"noise", "reasoning": str}
```

**Stage 2: Sonnet confirmation (high-severity only)**

Sonnet reviews Haiku's high-severity classifications. Can downgrade but not upgrade.

### Classification Routing

| Source Type | Method | Rationale |
|-------------|--------|-----------|
| `*_official.py` | Keywords | Clean, structured announcements |
| `newsapi.py` | Haiku → Sonnet | Noisy, needs context |
| `rss.py` | Haiku → Sonnet | Mixed quality |

---

## 7. Notifications & Integration

### Tiered Routing

| Severity | Channel | Timing |
|----------|---------|--------|
| High | Main Slack (`va-signals`) | Immediate |
| Medium | Weekly digest | Weekly |
| Low | Weekly digest | Weekly |
| Noise | Discarded | - |

### Slack Format (Immediate)

```
*State Intelligence Alert*

• *[Texas]* Texas Veterans Commission suspends PACT Act outreach
  _PACT Act_ | Source
  Triggers: suspend

• *[California]* CalVet reports 30% backlog in toxic exposure claims
  _PACT Act_ | Source
  Triggers: backlog
```

### Weekly Digest

Added to existing `src/reports.py`. Grouped by state, then by program.

### Dashboard

New endpoint: `GET /api/state/signals`
New tab: "State Intelligence" with state/severity filters.

---

## 8. Runner & Scheduling

### Cadence

Twice daily:
- Morning run (6am): Overnight news, previous afternoon announcements
- Evening run (6pm): Same-day announcements, afternoon news

### Makefile

```makefile
state-monitor:
	./.venv/bin/python -m src.state.runner

state-monitor-morning:
	./.venv/bin/python -m src.state.runner --run-type morning

state-monitor-evening:
	./.venv/bin/python -m src.state.runner --run-type evening
```

### Cron

```cron
0 6 * * * cd /path/to/va-signals && make state-monitor-morning
0 18 * * * cd /path/to/va-signals && make state-monitor-evening
```

---

## 9. Error Handling

### Fail-Closed Behavior

| Failure | Behavior | Alert |
|---------|----------|-------|
| NewsAPI down | Skip news, continue official | Log warning |
| State website changed | Skip source, log error | Alert after 3 consecutive failures |
| LLM API error | Fall back to keyword-only | Log warning |
| All sources fail for state | Mark state as ERROR | Immediate Slack alert |
| RSS feed timeout | Skip feed, continue others | Log warning |

### Source Health Tracking

```python
def check_source_health(source_id: str, success: bool) -> None:
    if count >= 3:
        notify_slack(f"Source {source_id} failed {count} times consecutively")
```

---

## 10. Testing

### Test Structure

```
tests/state/
├── test_common.py           # Keyword matching, dedup logic
├── test_classify.py         # Classification (keyword + mock LLM)
├── test_newsapi.py          # NewsAPI client (mocked responses)
├── test_rss.py              # RSS parsing (fixture feeds)
├── test_tx_official.py      # Texas source parsing
├── test_ca_official.py      # California source parsing
├── test_fl_official.py      # Florida source parsing
├── test_runner.py           # Integration tests
└── fixtures/
    ├── newsapi_response.json
    ├── tvc_news_page.html
    ├── calvet_newsroom.html
    └── sample_rss.xml
```

---

## 11. Bootstrap Sequence

| Week | Activity |
|------|----------|
| 1 | Deploy with logging only. Observe volume and classification accuracy. |
| 2 | Enable weekly digest only. Review quality before immediate alerts. |
| 3 | Enable high-severity immediate alerts. Monitor false positives. |
| 4+ | Tune keywords and LLM prompts based on patterns. |

### Initial Backfill

```python
def initial_backfill():
    """One-time 7-day backfill on first deployment."""
    for state in ["TX", "CA", "FL"]:
        signals = newsapi.search(state, lookback_days=7)
        store_signals(signals, suppress_immediate=True)
```

---

## 12. Future Expansion

Once TX/CA/FL monitoring is proven (60-90 days):

**States:** Add PA, OH, NY, NC, GA, VA, AZ (completes top 10)

**Programs:** Add GI Bill (state approving agencies), Homelessness (SSVF/HUD-VASH)

**Sources:** Add state legislature tracking (LegiScan API) for regulatory/legislative priorities
