# Oversight Monitor Cell — Design Document

## Overview

A parallel agent system that monitors congressional oversight activity and media coverage related to veterans benefits, claims processing, and VA operations. Surfaces insights only when there is a clear inflection point, deviation from historical oversight patterns, or an escalation that signals a meaningful shift in congressional posture or media narrative.

**Key constraints:**
- Only surface specific, dated external actions (hearing, markup, rulemaking, report, investigation, court opinion, formal statement)
- Filter out routine/baseline activity
- Treat undated explainers or general content as background — do not surface
- Always include explicit temporal context: source publication date, event date (if different), surfacing date
- Flag unknown timestamps rather than omitting

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    OVERSIGHT MONITOR CELL                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Source Agents (9)                                                      │
│  └── Each has source-specific timestamp extractor                       │
│  └── Outputs normalized events with precision flags                     │
│                          │                                              │
│                          ▼                                              │
│               ┌─────────────────────┐                                   │
│               │   Quality Gate      │ ── rejects → om_rejected          │
│               │ (pub_date required) │                                   │
│               └──────────┬──────────┘                                   │
│                          ▼                                              │
│               ┌─────────────────────┐                                   │
│               │   Deduplicator      │                                   │
│               │ (entity extraction, │                                   │
│               │  canonical event    │                                   │
│               │  matching)          │                                   │
│               └──────────┬──────────┘                                   │
│                          │                                              │
│            ┌─────────────┴─────────────┐                                │
│            ▼                           ▼                                │
│   ┌─────────────────┐        ┌─────────────────┐                       │
│   │ New canonical   │        │ Related coverage│                       │
│   │ event           │        │ (attach, don't  │                       │
│   └────────┬────────┘        │ alert)          │                       │
│            │                 └─────────────────┘                        │
│            ▼                                                            │
│   ┌─────────────────────┐                                               │
│   │  Haiku Pre-Filter   │                                               │
│   │  (VA-relevant?      │                                               │
│   │   dated action?)    │                                               │
│   └──────────┬──────────┘                                               │
│              ▼                                                          │
│   ┌─────────────────────┐                                               │
│   │  Escalation Check   │ ─── match ──▶ IMMEDIATE ALERT                │
│   │  (configurable      │                                               │
│   │   signals table)    │                                               │
│   └──────────┬──────────┘                                               │
│              │ no match                                                 │
│              ▼                                                          │
│   ┌─────────────────────┐                                               │
│   │  Bootstrap Mode?    │                                               │
│   │  (first 90 days)    │                                               │
│   └──────────┬──────────┘                                               │
│         yes/ \no                                                        │
│            /   \                                                        │
│           ▼     ▼                                                       │
│   ┌─────────┐ ┌─────────────────────┐                                  │
│   │ Store   │ │ Sonnet Classifier   │                                  │
│   │ silently│ │ (pattern deviation?)│                                  │
│   │ (build  │ └──────────┬──────────┘                                  │
│   │ baseline│            │                                              │
│   └─────────┘    ┌───────┴───────┐                                     │
│                  ▼               ▼                                      │
│           ┌──────────┐    ┌──────────┐                                 │
│           │ Routine  │    │ Deviation│                                 │
│           │ (store,  │    │ (surface │                                 │
│           │ no alert)│    │ in weekly│                                 │
│           └──────────┘    │ digest)  │                                 │
│                           └──────────┘                                  │
│                                                                         │
│  Storage:                                                               │
│  ├── om_events (all, 90-day rolling prune for routine)                 │
│  ├── om_related_coverage (linked derivative articles)                  │
│  ├── om_baselines (rolling summaries per source/theme)                 │
│  ├── om_rejected (audit log, 30-day prune)                             │
│  ├── om_escalation_signals (configurable triggers)                     │
│  └── om_digests (weekly digest history)                                │
└─────────────────────────────────────────────────────────────────────────┘
```

## Source Agents

| # | Agent | Source | API/Method | Update Frequency | Backfill |
|---|-------|--------|------------|------------------|----------|
| 1 | GAO | gao.gov | RSS + scrape | Daily | Full (2+ years) |
| 2 | VA OIG | va.gov/oig | RSS | Daily | Full (to 2015) |
| 3 | CRS | everycrsreport.com | Scrape | Daily | Full archive |
| 4 | Congressional Record | govinfo.gov | GovInfo API | Daily | Full archive |
| 5 | Committee Press | veterans.house.gov, veterans.senate.gov | Scrape | 2x daily | Best-effort 90 days |
| 6 | News (wire) | NewsAPI or MediaStack | API | 4x daily | 30 days + curated baseline |
| 7 | Investigative | ProPublica | RSS + API | Daily | Curated baseline |
| 8 | Trade Press | Military Times, Stars & Stripes | RSS | Daily | Curated baseline |
| 9 | Federal Circuit | cafc.uscourts.gov | RSS + PDF scrape | Daily | Full (VA cases) |

### Escalation Signals (Configurable)

| Signal | Type | Severity |
|--------|------|----------|
| criminal referral | phrase | critical |
| subpoena | keyword | critical |
| emergency hearing | phrase | critical |
| whistleblower | keyword | high |
| investigation launched | phrase | high |
| fraud | keyword | high |
| arrest | keyword | critical |
| first-ever | phrase | medium |
| reversal | keyword | medium |
| bipartisan letter | phrase | medium |
| precedential opinion | phrase | high |

## Baseline Detection

**Hybrid approach:**
1. **Rolling 90-day summary** — Compressed text summary of events per source/theme
2. **Hardcoded escalation signals** — Always surface regardless of baseline

**Deviation criteria (Sonnet classification):**
- Escalation in severity (audit → investigation → criminal referral)
- New topic not seen in baseline period
- Unusual actor involvement
- Reversal or contradiction of prior position
- Volume spike
- First-of-kind action
- Cross-branch convergence

## Notification Tiers

| Tier | Trigger | Delivery | Latency |
|------|---------|----------|---------|
| Immediate | Escalation signal match | Slack | < 1 hour |
| Weekly Digest | Pattern deviations | Slack + Email | Sunday 5 PM |

### Weekly Digest Format

Grouped by theme (not by source):
- Housing & Loan Guaranty
- Healthcare
- Benefits & Claims
- Oversight & Investigations
- Legal/Judicial

Each event includes:
- Title and type
- Three timestamps (published, event, surfaced) with precision flags
- 2-3 sentence summary
- Canonical references (FR doc, bill #, case #, CFR cite)
- "Why surfaced" explanation
- Related coverage count

## Database Schema

```sql
-- Canonical events (deduplicated, entity-centric)
CREATE TABLE IF NOT EXISTS om_events (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  theme TEXT,
  primary_source_type TEXT NOT NULL,
  primary_url TEXT NOT NULL,

  -- Temporal metadata with precision tracking
  pub_timestamp TEXT,
  pub_precision TEXT NOT NULL,       -- datetime, date, month, unknown
  pub_source TEXT NOT NULL,          -- extracted, inferred, missing
  event_timestamp TEXT,
  event_precision TEXT,
  event_source TEXT,

  -- Content
  title TEXT NOT NULL,
  summary TEXT,
  raw_content TEXT,

  -- Classification
  is_escalation BOOLEAN DEFAULT FALSE,
  escalation_signals TEXT,           -- JSON array
  is_deviation BOOLEAN DEFAULT FALSE,
  deviation_reason TEXT,
  canonical_refs TEXT,               -- JSON: {fr_doc, rin, bill, case, etc.}

  -- Surfacing
  surfaced BOOLEAN DEFAULT FALSE,
  surfaced_at TEXT,
  surfaced_via TEXT,                 -- immediate_alert, weekly_digest

  -- Metadata
  fetched_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Related coverage (derivative articles linked to canonical events)
CREATE TABLE IF NOT EXISTS om_related_coverage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  url TEXT NOT NULL,
  title TEXT,
  pub_timestamp TEXT,
  pub_precision TEXT,
  fetched_at TEXT NOT NULL,
  FOREIGN KEY (event_id) REFERENCES om_events(event_id),
  UNIQUE(event_id, url)
);

-- Rolling baseline summaries
CREATE TABLE IF NOT EXISTS om_baselines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_type TEXT NOT NULL,
  theme TEXT,
  window_start TEXT NOT NULL,
  window_end TEXT NOT NULL,
  event_count INTEGER NOT NULL,
  summary TEXT NOT NULL,
  topic_distribution TEXT,           -- JSON
  built_at TEXT NOT NULL,
  UNIQUE(source_type, theme, window_end)
);

-- Rejected events (audit log)
CREATE TABLE IF NOT EXISTS om_rejected (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_type TEXT NOT NULL,
  url TEXT NOT NULL,
  title TEXT,
  pub_timestamp TEXT,
  rejection_reason TEXT NOT NULL,    -- not_va_relevant, not_dated_action,
                                     -- temporal_incomplete, duplicate, routine
  routine_explanation TEXT,
  fetched_at TEXT NOT NULL,
  rejected_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Configurable escalation signals
CREATE TABLE IF NOT EXISTS om_escalation_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_pattern TEXT NOT NULL,
  signal_type TEXT NOT NULL,         -- keyword, phrase, entity_action
  severity TEXT NOT NULL,            -- critical, high, medium
  description TEXT,
  active BOOLEAN DEFAULT TRUE,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Weekly digest history
CREATE TABLE IF NOT EXISTS om_digests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  digest_type TEXT NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  event_ids TEXT NOT NULL,           -- JSON array
  theme_groups TEXT NOT NULL,        -- JSON
  delivered_at TEXT,
  delivered_via TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## Module Structure

```
src/
├── oversight/
│   ├── __init__.py
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                  # Abstract base class
│   │   ├── gao.py
│   │   ├── oig.py
│   │   ├── crs.py
│   │   ├── cong_record.py
│   │   ├── committee_press.py
│   │   ├── news_wire.py
│   │   ├── investigative.py
│   │   ├── trade_press.py
│   │   └── cafc.py
│   │
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── timestamp_extractor.py
│   │   ├── quality_gate.py
│   │   ├── deduplicator.py
│   │   ├── classifier.py            # Haiku + Sonnet
│   │   ├── escalation.py
│   │   └── thematic.py
│   │
│   ├── baseline/
│   │   ├── __init__.py
│   │   ├── builder.py
│   │   └── backfill.py
│   │
│   ├── output/
│   │   ├── __init__.py
│   │   ├── immediate_alert.py
│   │   ├── weekly_digest.py
│   │   └── formatters.py
│   │
│   └── db_helpers.py
│
└── run_oversight.py
```

## LLM Strategy

**Two-stage classification (cost-efficient):**

1. **Haiku pre-filter** — Fast, cheap check:
   - Is this VA-relevant?
   - Is this a dated action (not explainer/background)?

2. **Sonnet deviation check** — Deep analysis (only for candidates):
   - Compare to 90-day baseline
   - Is this routine or meaningful deviation?

## Bootstrap Sequence

### Phase 1: Backfill (Day 0)
- Fetch 90 days historical data from sources with API support
- Load curated baseline config for sources without backfill
- Store events without classification (save API costs)

### Phase 2: Escalation-Only (Days 1–90)
- Escalation signals active (immediate alerts work)
- Pattern deviation detection DISABLED
- System builds baseline from real data

### Phase 3: Full Operation (Day 91+)
- Full pipeline including Sonnet deviation check
- Weekly digest enabled
- Baseline rebuilt weekly with fresh 90-day window

## Temporal Metadata

Every surfaced event displays three timestamps:

```
Published:   Jan 20, 2026 10:00 AM ET  [extracted]
Event date:  Jan 15, 2026              [inferred from report text]
Surfaced:    Jan 20, 2026 2:30 PM ET   [system]
```

**Quality gate:** Events without determinable pub_timestamp are rejected.

**Precision tracking:**
- `datetime` — Full timestamp available
- `date` — Date only, no time
- `month` — Month/year only
- `range` — Date range (e.g., "January–March 2026")
- `unknown` — Could not determine

**Source tracking:**
- `extracted` — Parsed from source metadata
- `inferred` — Derived from text or publication date
- `missing` — Not available (flagged in output)

## Error Handling

| Stage | Error | Response |
|-------|-------|----------|
| Agent fetch | Network timeout | Retry 3x, then ERROR status |
| Agent fetch | 404 | Log, skip item, continue |
| Agent fetch | Rate limit | Backoff, retry |
| Pipeline | Haiku API error | Retry 2x, then skip |
| Pipeline | Sonnet API error | Retry 2x, defer to next run |
| Alert | Slack error | Retry 3x, queue for next attempt |

**Principle:** One agent failing does NOT block others. Fail closed — if we can't classify, don't surface.

## Storage & Pruning

| Table | Retention |
|-------|-----------|
| om_events (surfaced) | Indefinite |
| om_events (routine) | 90 days |
| om_related_coverage | Matches parent event |
| om_rejected | 30 days |
| om_baselines | Rolling (latest per source/theme) |
| om_digests | Indefinite |

## Output Examples

### Immediate Alert (Escalation)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 ESCALATION: GAO Criminal Referral — VA Contract Fraud
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Published:   Jan 20, 2026 10:00 AM ET  [extracted]
Event date:  Jan 15, 2026              [inferred from report text]
Surfaced:    Jan 20, 2026 2:30 PM ET   [system]

GAO Report GAO-26-106789 refers VA contract fraud case to DOJ for
potential criminal prosecution. Investigation found $4.2M in
fraudulent billing in Community Care Network contracts.

Source: https://gao.gov/products/gao-26-106789
Related: 2 articles (Military Times, AP)

Refs: GAO-26-106789 | 38 U.S.C. § 3701 | Docket VA-2024-VBA-0089
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Weekly Digest

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VA OVERSIGHT WEEKLY DIGEST
Period: Jan 13–20, 2026
Generated: Jan 20, 2026 5:00 PM ET
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 SUMMARY
• 3 events surfaced (1 escalation, 2 pattern deviations)
• 12 events filtered as routine
• 4 events rejected (2 undated, 2 not VA-relevant)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏠 HOUSING & LOAN GUARANTY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. VA Withdraws Servicer Tier Ranking ANPRM
   Type: Regulatory withdrawal
   Published: Jan 20, 2026 | Event: Jan 20, 2026 | Surfaced: Jan 20, 2026

   VA formally withdrew the 2022 ANPRM on servicer tier rankings.
   Future rulemaking will start fresh.

   Refs: FR 2026-01007 | 38 CFR 36.4318 | RIN 2900-AR42
   Why surfaced: First withdrawal of VA loan rulemaking since 2019

2. Subcommittee Hearing: Economic Opportunity
   Type: Legislative hearing
   Published: Jan 14, 2026 | Event: Jan 21, 2026 | Surfaced: Jan 20, 2026

   Agenda includes discussion drafts for quarterly VA housing loan
   reporting and Affordable Housing Guarantee Act.

   Refs: HHRG-119-VR10-20260121 | H.R. 982, H.R. 5634
   Why surfaced: Housing reporting mandate aligns with ANPRM withdrawal

3. McKinney v. Secretary — TSGLI Coverage Denied
   Type: Court opinion (precedential)
   Published: Jan 14, 2026 | Event: Jan 14, 2026 | Surfaced: Jan 20, 2026

   Federal Circuit upholds VA denial of rulemaking petition to expand
   TSGLI to illness caused by explosives post-service.

   Refs: CAFC 23-1930 | 38 U.S.C. § 1980A | 38 CFR 9.20
   Why surfaced: Precedential; closes pathway for TSGLI expansion

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## CLI Interface

```bash
# Daily operation
python -m src.run_oversight                    # Run all agents + pipeline

# Single agent
python -m src.run_oversight --agent gao        # Run one agent only

# Bootstrap
python -m src.run_oversight --backfill         # Historical data import

# Manual digest
python -m src.run_oversight --digest           # Force weekly digest

# Status
python -m src.run_oversight --status           # Show system status

# Makefile target
make oversight                                 # Alias for run_oversight
```

## Risks Addressed

| Risk | Mitigation |
|------|------------|
| Cold start (90 days to baseline) | Backfill + escalation-only mode during bootstrap |
| Deduplication (same event, 5 sources) | Entity-centric canonical events + source hierarchy |
| Temporal gaps (missing timestamps) | Source-specific extractors + quality gate + explicit unknown flags |
| LLM inconsistency | Logged prompts/responses, deterministic escalation signals |
| Source fragility | Independent agents, graceful degradation |
| Alert fatigue | Tiered notification, thematic grouping |

## Testing Strategy

```
tests/oversight/
├── test_agents/           # Mock sources, verify parsing
├── test_pipeline/         # Each stage isolated
│   ├── test_timestamp_extractor.py
│   ├── test_quality_gate.py
│   ├── test_deduplicator.py
│   ├── test_classifier.py
│   └── test_escalation.py
├── test_output/           # Format validation
└── test_integration/      # End-to-end with mocks
```

## Implementation Order

1. Schema + db_helpers
2. Base agent class + GAO agent (simplest API)
3. Pipeline: quality_gate → deduplicator → escalation
4. Immediate alert output
5. Remaining agents (OIG, CAFC, CRS, etc.)
6. Haiku pre-filter
7. Baseline builder + backfill
8. Sonnet deviation classifier
9. Weekly digest + thematic grouping
10. Dashboard integration
