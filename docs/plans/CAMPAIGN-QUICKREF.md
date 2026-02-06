# VA Signals Campaign Plan - Quick Reference

## End State
Veterans affairs policy changes detected within 24-72 hours. <5 min/day human attention.

## 5 Lines of Effort

| LOE | Name | Objective | Status |
|-----|------|-----------|--------|
| **1** | Federal Authority | 100% detection of binding VA federal actions | ✅ Operational |
| **2** | Oversight Intel | GAO/OIG/CRS/CAFC coverage with 90-day baseline | ✅ 9/9 agents + baselines |
| **3** | State Implementation | Top-10 states monitored | ✅ 10/10 |
| **4** | Behavioral Intel | Predict policy shifts via rhetoric analysis | ✅ Operational |
| **5** | Command & Control | Unified ops picture, self-sustaining | ✅ Operational |

## 4 Phases (90 days from 22 Jan 2026)

```
Phase I:   CONSOLIDATION  (Weeks 1-4)   - Complete oversight agents, build baselines
Phase II:  EXPANSION      (Weeks 5-8)   - Add PA/OH/NY, cross-source dedup
Phase III: OPTIMIZATION   (Weeks 9-12)  - Complete 10 states, predictive indicators
Phase IV:  SUSTAINMENT    (Ongoing)     - <5 min/day attention, continuous ops
```

## Phase I Status (Complete — 5 Feb 2026)

1. [x] GAO reports agent → operational (25 reports in DB)
2. [x] VA OIG reports agent → operational (vaoig.gov, 10 reports)
3. [x] CRS reports agent → configured (everycrsreport.com RSS)
4. [x] Congressional Record agent → operational (Congress.gov API v3)
5. [x] Committee Press agent → operational (HVAC + SVAC scraping, 17 events)
6. [x] News Wire agent → operational (NewsAPI.org, 169 events, 6 escalations)
7. [x] Trade Press agent → operational (Military Times, Stars & Stripes)
8. [x] Investigative agent → operational (ProPublica)
9. [x] CAFC agent → operational (RSS + HTML fallback, 5 VA cases)
10. [x] Auth hardening complete (Cloud Run rev 34, 60 tests passing)
11. [x] CI/CD pipeline updated (oversight + state monitor in daily workflow)
12. [x] 90-day baseline computation — 8/9 sources baselined (CRS = 0 VA events, expected)
13. [ ] 7 consecutive days zero critical failures (tracking from 5 Feb)

## Phase II Status (Complete — 5 Feb 2026)

1. [x] Pennsylvania sources (730K vets) — PA DMVA scraper + 3 NewsAPI queries + 2 RSS feeds (8 signals)
2. [x] Ohio sources (680K vets) — ODVS scraper (disabled, site 404) + 3 NewsAPI queries + 2 RSS feeds (3 signals)
3. [x] New York sources (670K vets) — NY DVS scraper + 3 NewsAPI queries + 2 RSS feeds (41 signals, 1 HIGH)
4. [ ] Cross-source deduplication refinement

## Phase III Status (Complete — 5 Feb 2026)

1. [x] North Carolina sources (630K vets) — NCDMVA scraper + 3 NewsAPI queries + 2 RSS feeds (21 signals)
2. [x] Georgia sources (590K vets) — GDVS scraper + 3 NewsAPI queries + 2 RSS feeds (21 signals)
3. [x] Virginia sources (580K vets) — DVS scraper (disabled, site 403) + 3 NewsAPI queries + 2 RSS feeds (6 signals)
4. [x] Arizona sources (480K vets) — DVS scraper (disabled, site 403) + 3 NewsAPI queries + 2 RSS feeds (3 signals)

## Key Metrics

| Metric | Target | Current |
|--------|--------|---------|
| FR detection latency | <24 hr | ~12 hr ✅ |
| Oversight currency | <72 hr | ~24 hr ✅ (9/9 agents) |
| State coverage | 10 states | 10 states ✅ (TX, CA, FL, PA, OH, NY, NC, GA, VA, AZ) |
| Alert precision | >95% | ~90% ⚠️ |
| Daily ops attention | <5 min | ~8 min ⚠️ |
| Total oversight events | — | 240 |
| Escalations detected | — | 6 |
| State signals (new) | — | 103 (PA:8, OH:3, NY:41, NC:21, GA:21, VA:6, AZ:3) |
| Baselines computed | 9 sources | 8/9 ✅ (CRS = 0 VA events) |

## Commander's Intent

> "Monitor continuously. Interrupt selectively. Speak only when it changes outcomes."

**Acceptable:** 24-72hr latency on non-binding signals, occasional false negatives on low-severity

**Unacceptable:** Missing binding Title 38 rules, alert fatigue, lost provenance

## Full Plan
See: `docs/plans/2026-01-22-operational-design-campaign-plan.md`
