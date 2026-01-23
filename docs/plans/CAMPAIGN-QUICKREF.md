# VA Signals Campaign Plan - Quick Reference

## End State
Veterans affairs policy changes detected within 24-72 hours. <5 min/day human attention.

## 5 Lines of Effort

| LOE | Name | Objective | Status |
|-----|------|-----------|--------|
| **1** | Federal Authority | 100% detection of binding VA federal actions | ✅ Operational |
| **2** | Oversight Intel | GAO/OIG/CRS/CAFC coverage with 90-day baseline | ⚠️ 5/9 agents |
| **3** | State Implementation | Top-10 states monitored | ⚠️ 3/10 |
| **4** | Behavioral Intel | Predict policy shifts via rhetoric analysis | ✅ Operational |
| **5** | Command & Control | Unified ops picture, self-sustaining | ✅ Operational |

## 4 Phases (90 days)

```
Phase I:   CONSOLIDATION  (Weeks 1-4)   - Complete oversight agents, build baselines
Phase II:  EXPANSION      (Weeks 5-8)   - Add PA/OH/NY, cross-source dedup
Phase III: OPTIMIZATION   (Weeks 9-12)  - Complete 10 states, predictive indicators
Phase IV:  SUSTAINMENT    (Ongoing)     - <5 min/day attention, continuous ops
```

## Phase I Priority Tasks (This Week)

1. [x] GAO reports agent → operational (25 reports in DB)
2. [x] VA OIG reports agent → operational (FIXED: vaoig.gov, 10 reports in DB)
3. [x] CRS reports agent → operational (everycrsreport.com RSS, filtering for VA)
4. [ ] Congressional Record agent → needs GovInfo API
5. [x] Trade Press agent → operational (Military Times, Stars & Stripes)
6. [x] Investigative agent → operational (ProPublica)

## Key Metrics

| Metric | Target | Current |
|--------|--------|---------|
| FR detection latency | <24 hr | ~12 hr ✅ |
| Oversight currency | <72 hr | ~24 hr ✅ (5/9 agents) |
| State coverage | 10 states | 3 states ⚠️ |
| Alert precision | >95% | ~90% ⚠️ |
| Daily ops attention | <5 min | ~10 min ⚠️ |

## Commander's Intent

> "Monitor continuously. Interrupt selectively. Speak only when it changes outcomes."

**Acceptable:** 24-72hr latency on non-binding signals, occasional false negatives on low-severity

**Unacceptable:** Missing binding Title 38 rules, alert fatigue, lost provenance

## Full Plan
See: `docs/plans/2026-01-22-operational-design-campaign-plan.md`
