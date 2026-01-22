# VA Signals Operational Design & Campaign Plan

> **Classification:** UNCLASSIFIED // FOR OFFICIAL USE ONLY
> **Effective Date:** 22 January 2026
> **Plan Version:** 1.0

---

## Executive Summary

This operational design applies the principles of operational art to the VA Signals intelligence system. It integrates ends, ways, and means across the strategic, operational, and tactical levels to achieve decision advantage in Veterans Affairs policy monitoring.

The campaign consists of **4 Phases** across **5 Lines of Effort (LOEs)**, designed to transition from current partial capability to full operational capacity within 90 days, with sustained operations thereafter.

---

## SECTION I: STRATEGIC CONTEXT

### 1.1 National Strategic End State

**Desired Condition:** Veterans receive timely, accurate benefits and services as mandated by law, with policy changes detected and surfaced before implementation gaps emerge.

**Problem Statement:** The VA policy landscape spans federal rulemaking (FR/eCFR), legislative action (bills/hearings), oversight bodies (GAO/OIG/CRS), and 50 state implementations. No single human or team can monitor this attack surface comprehensively. Signals get lost. Implementation lags go undetected. Veterans suffer from information asymmetry.

### 1.2 Operational End State

**Desired Condition:** VA Signals operates as an always-on, fail-closed intelligence system that:
- Detects 100% of binding federal changes within 24 hours of publication
- Tracks legislative and oversight signals with 72-hour currency
- Monitors implementation signals in top-10 veteran population states
- Alerts only when decision space changes (zero alert fatigue)
- Maintains complete audit trail for accountability

**Success Criteria:**
1. Zero missed FR documents affecting Title 38
2. <24hr latency from source publication to system detection
3. <1% false positive rate on high-severity alerts
4. 100% provenance chain on all surfaced signals
5. Sustained operation with <5 min/day human oversight

### 1.3 Current Situation (METT-TC Analysis)

| Factor | Assessment |
|--------|------------|
| **Mission** | Comprehensive VA policy signal detection and routing |
| **Enemy** | Information entropy, source fragmentation, alert fatigue, implementation lag |
| **Terrain** | Federal (FR, eCFR, Congress, GAO/OIG) + State (50 jurisdictions) + News |
| **Troops** | Automated agents (9 oversight, 3 state, 4 federal) + ML classifiers + routing engine |
| **Time** | 90-day sprint to full operational capability; indefinite sustainment |
| **Civilians** | Veterans (24M), VSOs, policy staff, congressional offices |

---

## SECTION II: OPERATIONAL DESIGN ELEMENTS

### 2.1 Center of Gravity Analysis

#### Friendly Center of Gravity
**Provenance-validated signal detection** — The system's critical capability is the ability to detect, validate, and route signals with complete audit trail. This is enabled by:
- Approved sources list (authority validation)
- Fail-closed architecture (no fabrication)
- Two-gate doctrine (authority → change detection)

**Critical Vulnerabilities:**
- Source API changes/deprecation
- Rate limiting/blocking by sources
- LLM API availability
- Single-point-of-failure database

#### Enemy Center of Gravity
**Information entropy** — The adversarial condition is the natural tendency of policy signals to fragment, duplicate, contradict, and overwhelm. This manifests as:
- Cross-source duplication (same event, multiple reports)
- Noise flooding (routine actions masking significant changes)
- Temporal confusion (publication date ≠ effective date ≠ surfaced date)
- Implementation gaps (federal mandate, state non-compliance)

### 2.2 Decisive Points

| Phase | Decisive Point | Enabling Condition |
|-------|---------------|-------------------|
| I | Oversight agents operational | All 9 agents ingesting with backfill complete |
| II | Cross-source deduplication live | Entity extraction matching related coverage |
| III | State expansion complete | Top-10 states monitored with classification |
| IV | Self-sustaining ops | <5 min/day human attention, zero drift |

### 2.3 Operational Approach

**Combined approach:** Direct action on data sources + Indirect action through pattern recognition

- **Direct:** Systematic source enumeration, API integration, web scraping
- **Indirect:** ML-based anomaly detection, semantic analysis, baseline-relative alerting

---

## SECTION III: LINES OF EFFORT

### LOE 1: FEDERAL AUTHORITY MONITORING
*"Know the law before they publish it"*

**Objective:** Achieve 100% detection of binding VA-related federal actions within 24 hours.

**Current State:** FR delta detection operational. eCFR tracking implemented. Bills and hearings live.

**End State:** Complete federal signal coverage including proposed rules, final rules, notices, committee reports, and floor actions.

| Task | Priority | Status | Target |
|------|----------|--------|--------|
| FR daily delta detection | Critical | ✅ COMPLETE | Sustained |
| eCFR Title 38 change tracking | High | ✅ COMPLETE | Sustained |
| Congress bills tracking | High | ✅ COMPLETE | Sustained |
| Committee hearings monitoring | High | ✅ COMPLETE | Sustained |
| Congressional Record floor debate | Medium | 🔄 PLANNED | Phase I |
| Committee markup tracking | Medium | 🔄 PLANNED | Phase II |
| CBO score integration | Low | 🔄 PLANNED | Phase III |

**Measures of Effectiveness (MOEs):**
- FR detection latency: <24 hours (current: ~12 hours)
- Bills tracking currency: <48 hours (current: ~24 hours)
- Zero missed binding documents (current: verified)

---

### LOE 2: OVERSIGHT INTELLIGENCE
*"See what the watchers see"*

**Objective:** Maintain awareness of all GAO, OIG, CRS, and judicial oversight affecting VA.

**Current State:** 9 agents specified, partial implementation. Pipeline stages complete.

**End State:** Real-time ingestion of oversight signals with 90-day baseline, anomaly detection, and thematic weekly digests.

| Task | Priority | Status | Target |
|------|----------|--------|--------|
| GAO reports agent | Critical | ⚠️ PARTIAL | Phase I Week 1 |
| VA OIG reports agent | Critical | ⚠️ PARTIAL | Phase I Week 1 |
| CRS reports agent | High | ⚠️ PARTIAL | Phase I Week 2 |
| Congressional Record agent | High | 🔄 PLANNED | Phase I Week 2 |
| Committee press releases | Medium | 🔄 PLANNED | Phase I Week 3 |
| News wire integration | Medium | ⚠️ PARTIAL | Phase I Week 3 |
| CAFC VA opinions | Low | 🔄 PLANNED | Phase II |
| Investigative journalism | Low | 🔄 PLANNED | Phase II |
| 90-day baseline build | Critical | 🔄 PLANNED | Phase I Week 4 |

**MOEs:**
- Oversight signal detection: <72 hours from publication
- Backfill completeness: 100% of 90-day history
- Weekly digest quality: Actionable thematic grouping

---

### LOE 3: STATE IMPLEMENTATION TRACKING
*"Follow the money to the veteran"*

**Objective:** Detect state-level implementation signals, gaps, and innovations across top-10 veteran population states.

**Current State:** TX/CA/FL operational with 2x daily runs. Classification pipeline live.

**End State:** Top-10 states monitored (covering ~55% of US veteran population) with state-specific source adaptation.

| Task | Priority | Status | Target |
|------|----------|--------|--------|
| Texas sources | Critical | ✅ COMPLETE | Sustained |
| California sources | Critical | ✅ COMPLETE | Sustained |
| Florida sources | Critical | ✅ COMPLETE | Sustained |
| Pennsylvania sources | High | 🔄 PLANNED | Phase II |
| Ohio sources | High | 🔄 PLANNED | Phase II |
| New York sources | High | 🔄 PLANNED | Phase II |
| North Carolina sources | Medium | 🔄 PLANNED | Phase III |
| Georgia sources | Medium | 🔄 PLANNED | Phase III |
| Virginia sources | Medium | 🔄 PLANNED | Phase III |
| Arizona sources | Medium | 🔄 PLANNED | Phase III |
| State bill tracking (LegiScan) | High | 🔄 PLANNED | Phase II |

**State Priority Ranking (by veteran population):**
1. California (1.6M) ✅
2. Texas (1.5M) ✅
3. Florida (1.5M) ✅
4. Pennsylvania (730K)
5. Ohio (680K)
6. New York (670K)
7. North Carolina (650K)
8. Georgia (640K)
9. Virginia (630K)
10. Arizona (520K)

**MOEs:**
- State coverage: 10 states (Phase III complete)
- Classification accuracy: >85% (current: ~75%)
- Implementation gap detection: <7 days

---

### LOE 4: BEHAVIORAL INTELLIGENCE
*"Watch the watchers change"*

**Objective:** Detect shifts in congressional rhetoric, committee focus, and policy framing before they manifest as legislation.

**Current State:** Agenda drift detection operational with improved filtering. 66 members tracked, 9 deviations flagged.

**End State:** Predictive indicators of policy direction based on semantic trajectory analysis.

| Task | Priority | Status | Target |
|------|----------|--------|--------|
| Agenda drift core | Critical | ✅ COMPLETE | Sustained |
| Utterance filtering (<100 char) | High | ✅ COMPLETE | Sustained |
| Baseline rebuild automation | Medium | 🔄 PLANNED | Phase I |
| Cross-member correlation | Medium | 🔄 PLANNED | Phase II |
| Topic emergence detection | Low | 🔄 PLANNED | Phase III |
| Witness testimony tracking | Low | 🔄 PLANNED | Phase III |

**MOEs:**
- False positive rate: <50% (current: ~44%)
- Member coverage: HVAC + SVAC complete
- Lead time on policy shifts: >2 weeks

---

### LOE 5: COMMAND & CONTROL
*"Orchestrate the sensors, own the picture"*

**Objective:** Unified operational picture with minimal human attention required.

**Current State:** Dashboard live with Federal/State tabs. Signals routing engine complete. Slack alerts operational.

**End State:** Self-healing, self-reporting system requiring <5 min/day human oversight.

| Task | Priority | Status | Target |
|------|----------|--------|--------|
| Dashboard Federal view | Critical | ✅ COMPLETE | Sustained |
| Dashboard State view | Critical | ✅ COMPLETE | Sustained |
| Slack high-severity alerts | Critical | ✅ COMPLETE | Sustained |
| Email weekly digests | High | ✅ COMPLETE | Sustained |
| Signals routing engine | Critical | ✅ COMPLETE | Sustained |
| Source health monitoring | High | ✅ COMPLETE | Sustained |
| Self-healing retries | Medium | ⚠️ PARTIAL | Phase I |
| Anomaly self-detection | Medium | 🔄 PLANNED | Phase II |
| Ops runbook automation | Low | 🔄 PLANNED | Phase III |

**MOEs:**
- Daily human attention: <5 minutes
- Alert precision: >95% actionable
- System uptime: >99.5%

---

## SECTION IV: PHASING

### Phase I: CONSOLIDATION (Weeks 1-4)
*"Secure what we have, fill the gaps"*

**Objective:** Complete oversight agent deployment, establish 90-day baselines.

**Main Effort:** LOE 2 (Oversight Intelligence)

**Supporting Efforts:** LOE 1 sustainment, LOE 5 hardening

**Key Tasks:**
- [ ] Week 1: GAO + OIG agents fully operational with backfill
- [ ] Week 2: CRS + Congressional Record agents operational
- [ ] Week 3: Committee press + News wire agents operational
- [ ] Week 4: 90-day baseline complete, escalation-only mode exits

**Transition Criteria:**
- All 9 oversight agents ingesting
- 90-day baseline populated
- Zero critical source failures for 7 consecutive days

---

### Phase II: EXPANSION (Weeks 5-8)
*"Extend the perimeter, deepen the analysis"*

**Objective:** Add 3 more states, enable cross-source deduplication, add judicial tracking.

**Main Effort:** LOE 3 (State Implementation)

**Supporting Efforts:** LOE 2 (CAFC), LOE 4 (cross-member correlation)

**Key Tasks:**
- [ ] Week 5: Pennsylvania sources operational
- [ ] Week 6: Ohio + New York sources operational
- [ ] Week 7: Cross-source deduplication live (entity extraction)
- [ ] Week 8: CAFC VA opinions tracking live

**Transition Criteria:**
- 6 states operational (TX, CA, FL, PA, OH, NY)
- Cross-source deduplication reducing noise by >30%
- Entity extraction accuracy >80%

---

### Phase III: OPTIMIZATION (Weeks 9-12)
*"Sharpen the blade, reduce the noise"*

**Objective:** Complete top-10 state coverage, enable predictive indicators, automate operations.

**Main Effort:** LOE 3 (remaining states) + LOE 4 (predictive)

**Supporting Efforts:** LOE 5 (automation)

**Key Tasks:**
- [ ] Week 9: NC + GA sources operational
- [ ] Week 10: VA + AZ sources operational
- [ ] Week 11: Topic emergence detection enabled
- [ ] Week 12: Ops runbook automation complete

**Transition Criteria:**
- 10 states operational
- Predictive indicators generating leads
- Daily ops attention <5 minutes

---

### Phase IV: SUSTAINMENT (Ongoing)
*"Maintain the watch, adapt to change"*

**Objective:** Continuous operation with minimal drift, maximum reliability.

**Key Activities:**
- Daily: Automated runs, health checks, alert routing
- Weekly: Digest generation, baseline refresh, performance review
- Monthly: Source health audit, coverage gap analysis
- Quarterly: Architecture review, capability expansion planning

**Steady State Metrics:**
| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| FR detection latency | <24 hr | >48 hr |
| Oversight currency | <72 hr | >1 week |
| State coverage | 10 states | <8 states |
| Alert precision | >95% | <90% |
| System uptime | >99.5% | <99% |
| Daily ops attention | <5 min | >15 min |

---

## SECTION V: SYNCHRONIZATION MATRIX

```
WEEK:        1    2    3    4    5    6    7    8    9   10   11   12   SS
─────────────────────────────────────────────────────────────────────────
LOE 1:      [=== SUSTAIN ================================================>
  FR        ████████████████████████████████████████████████████████████
  Bills     ████████████████████████████████████████████████████████████
  Hearings  ████████████████████████████████████████████████████████████
  CongRec        ████████████████████████████████████████████████████████

LOE 2:      [=== BUILD ===][=== BASELINE ===][=== SUSTAIN ===============>
  GAO       ████
  OIG       ████
  CRS            ████
  CommPress           ████
  News            ████
  CAFC                              ████
  90d-base            ████████████

LOE 3:      [= SUSTAIN =][===== EXPAND =====][=== COMPLETE ==][= SUSTAIN >
  TX/CA/FL  ████████████████████████████████████████████████████████████
  PA                  ████████████████████████████████████████████████████
  OH/NY                    ████████████████████████████████████████████████
  NC/GA                                        ████████████████████████████
  VA/AZ                                             ████████████████████████
  LegiScan                 ████████████████████████████████████████████████

LOE 4:      [=== SUSTAIN ===][=== ENHANCE ===][=== PREDICT ==][= SUSTAIN >
  Drift     ████████████████████████████████████████████████████████████
  X-member                      ████████████████████████████████████████
  Topics                                            ████████████████████

LOE 5:      [=== HARDEN ====][=== AUTOMATE ===][=== OPTIMIZE =][= SUSTAIN >
  Dashboard ████████████████████████████████████████████████████████████
  Routing   ████████████████████████████████████████████████████████████
  Alerts    ████████████████████████████████████████████████████████████
  Self-heal      ████████████████████████████████████████████████████████
  Runbook                                           ████████████████████

PHASE:      [=== I: CONSOLIDATION ===][=== II: EXPANSION ===][= III: OPT =]
```

---

## SECTION VI: RISK ASSESSMENT

### Critical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Source API deprecation | Medium | High | Multi-source redundancy, RSS fallbacks |
| Rate limiting/blocking | High | Medium | Distributed timing, caching, fallback scrapers |
| LLM API outage | Low | High | Keyword fallback classification, queue pending |
| Database corruption | Low | Critical | Daily backups, WAL mode, integrity checks |
| Alert fatigue regression | Medium | High | Strict suppression policy, baseline discipline |

### Operational Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Scope creep | High | Medium | YAGNI doctrine, phase gates |
| Technical debt | Medium | Medium | TDD mandate, code review |
| Single maintainer | High | High | Documentation, decision log, runbooks |
| State source fragmentation | High | Medium | Standardized adapter pattern |

---

## SECTION VII: COMMAND RELATIONSHIPS

### Operational Control

```
┌─────────────────────────────────────────────────────────┐
│                    HUMAN OPERATOR                        │
│            (Strategic Direction, Exception Handling)     │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                 SIGNALS ROUTING ENGINE                   │
│           (Tactical Decision, Alert Routing)             │
├─────────────┬─────────────┬─────────────┬───────────────┤
│   LOE 1     │   LOE 2     │   LOE 3     │    LOE 4      │
│  Federal    │  Oversight  │   State     │  Behavioral   │
│   Agents    │   Agents    │   Agents    │    Agents     │
└─────────────┴─────────────┴─────────────┴───────────────┘
```

### Decision Authority Matrix

| Decision Type | Authority | Escalation |
|---------------|-----------|------------|
| Source addition (approved list) | System | None |
| Source removal | Human | N/A |
| Alert threshold tuning | System + Human | Review weekly |
| New state onboarding | Human | N/A |
| Architecture changes | Human | N/A |
| Emergency source disable | System | Alert human |

---

## SECTION VIII: LOGISTICS & SUSTAINMENT

### Infrastructure Requirements

| Resource | Current | Required | Gap |
|----------|---------|----------|-----|
| Compute | Local Mac | Local Mac | None |
| Database | SQLite | SQLite | None |
| LLM API | Claude (Haiku/Sonnet) | Claude | None |
| News API | NewsAPI.org | NewsAPI.org | None |
| Slack | Bot configured | Bot configured | Token needed |
| Email | SMTP configured | SMTP configured | None |

### Operational Tempo

| Cycle | Frequency | Duration | Attention |
|-------|-----------|----------|-----------|
| FR delta check | Daily 6am | ~2 min | Automated |
| State monitor | 2x daily | ~3 min | Automated |
| Hearings check | Daily | ~1 min | Automated |
| Bills check | Daily | ~1 min | Automated |
| Oversight check | Daily | ~5 min | Automated |
| Agenda drift | Weekly | ~10 min | Automated |
| Weekly digest | Sunday | ~5 min | Human review |
| Health check | Hourly | ~10 sec | Automated |

---

## SECTION IX: ASSESSMENT FRAMEWORK

### Weekly Battle Rhythm

| Day | Activity | Owner |
|-----|----------|-------|
| Monday | Review weekend alerts, clear queue | Human |
| Tuesday | Source health audit | Automated |
| Wednesday | Mid-week status check | Automated |
| Thursday | Emerging issues triage | Human |
| Friday | Weekly metrics compilation | Automated |
| Saturday | Baseline refresh (overnight) | Automated |
| Sunday | Weekly digest generation + review | Human |

### Key Performance Indicators

**Detection KPIs:**
- FR latency: Time from GovInfo publication to system detection
- Oversight currency: Age of most recent oversight signal
- State coverage: % of top-10 states with active monitoring

**Quality KPIs:**
- Alert precision: % of alerts that are actionable
- False positive rate: % of flagged signals that are noise
- Deduplication effectiveness: % reduction in redundant signals

**Operational KPIs:**
- System uptime: % of scheduled runs completing successfully
- Human attention: Minutes per day of required human intervention
- Backlog depth: Number of unprocessed signals in queue

---

## SECTION X: COMMANDER'S INTENT

**Purpose:** Achieve persistent, comprehensive awareness of all policy signals affecting American veterans.

**Method:** Employ a disciplined, fail-closed intelligence system that monitors authoritative sources continuously, classifies signals by severity and actionability, and alerts human operators only when decision space changes.

**End State:**
- Veterans affairs policy changes are detected within 24-72 hours of publication
- Implementation gaps between federal mandates and state execution are visible
- Behavioral shifts in congressional oversight are tracked predictively
- Human operators spend <5 minutes daily maintaining situational awareness
- Complete audit trail enables accountability and after-action review

**Key Tasks:**
1. Complete oversight agent deployment (Phase I)
2. Expand to 10 states (Phase II-III)
3. Enable predictive behavioral intelligence (Phase III)
4. Achieve self-sustaining operations (Phase IV)

**Acceptable Risk:**
- Tolerate occasional false negatives on low-severity signals
- Accept 24-72 hour latency on non-binding signals
- Allow automated systems to make routine classification decisions

**Unacceptable Risk:**
- Missing any binding federal rule affecting Title 38
- Alert fatigue causing human operators to ignore system
- Loss of provenance chain on any surfaced signal
- System drift without detection

---

## ANNEXES

### Annex A: Approved Sources List
See `config/approved_sources.yaml`

### Annex B: Database Schema
See `schema.sql`

### Annex C: API Integrations
- GovInfo: FR Bulk XML, Congressional Record
- Congress.gov: Bills, Hearings
- NewsAPI.org: Wire services
- Claude API: Haiku (classification), Sonnet (analysis)

### Annex D: Decision Log
See `docs/DECISIONS.md`

### Annex E: Operational Runbooks
*To be developed Phase III*

---

**AUTHENTICATION:**

Plan prepared by operational design process
Effective: 22 January 2026
Review: 22 April 2026 (Quarterly)

---

*"Monitor continuously. Interrupt selectively. Speak only when it changes outcomes."*
