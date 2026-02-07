# EXPERT 2: Intelligence Pipeline Analysis

**Analyst**: AI Scientist & Statistician
**Date**: 2026-02-07
**Scope**: Signal detection chain, LLM integration quality, deviation detection, oversight escalation, production throughput

---

## 1. Pipeline Quality Scorecard by Source

### Methodology

Each source is graded on five dimensions (0-10 scale):
- **Detection Latency**: How fast new signals are detected after publication
- **Classification Quality**: Accuracy of relevance/severity assessment
- **Data Freshness Guarantee**: Whether the system enforces temporal integrity
- **Deduplication Effectiveness**: How well redundant signals are suppressed
- **Production Readiness**: End-to-end path from raw signal to CEO brief / anchor pack

| Source | Detection | Classification | Freshness | Dedup | Production | **Avg** |
|--------|-----------|---------------|-----------|-------|------------|---------|
| **GAO** (RSS) | 7 | 8 | 7 | 9 | 8 | **7.8** |
| **VA OIG** (RSS) | 7 | 8 | 7 | 9 | 8 | **7.8** |
| **CRS** | 6 | 8 | 6 | 8 | 7 | **7.0** |
| **CAFC** | 6 | 7 | 6 | 8 | 7 | **6.8** |
| **BVA** | 6 | 7 | 6 | 8 | 7 | **6.8** |
| **Congressional Record** | 7 | 7 | 7 | 7 | 7 | **7.0** |
| **Committee Press** | 7 | 7 | 7 | 6 | 7 | **6.8** |
| **News Wire** | 8 | 6 | 5 | 5 | 6 | **6.0** |
| **Investigative** | 6 | 6 | 5 | 5 | 6 | **5.6** |
| **Trade Press** | 6 | 6 | 5 | 5 | 6 | **5.6** |
| **Federal Register** | 9 | 8 | 9 | 8 | 9 | **8.6** |
| **eCFR** | 8 | 7 | 8 | 7 | 7 | **7.4** |
| **Congressional Bills** | 8 | 8 | 8 | 8 | 8 | **8.0** |
| **Hearings** | 7 | 7 | 7 | 7 | 8 | **7.2** |
| **State Intel (10 states)** | 7 | 7 | 6 | 7 | 7 | **6.8** |
| **Agenda Drift** | 6 | 8 | 5 | N/A | 6 | **6.3** |
| **LDA Lobbying** | 7 | 7 | 7 | 7 | 6 | **6.8** |

**System-wide average: 7.0/10** -- This is a strong baseline for a production intelligence platform.

### Key Observations

1. **Federal Register is the strongest pipeline** (8.6/10) -- API-based, official source, strong dedup via doc_id, direct path to CEO briefs. This is the gold standard the other sources should be measured against.

2. **News/Investigative sources are weakest** (5.6-6.0/10) -- Lower classification accuracy (no structured metadata), weaker dedup (no canonical identifiers), inconsistent timestamps. This is expected for unstructured sources.

3. **State Intelligence is surprisingly capable** (6.8/10) -- 10 states with 3 source types each (official, NewsAPI, RSS), parallel execution, keyword + LLM hybrid classification. The main weakness is that LLM classification uses `claude-3-haiku-20240307` (the legacy model, not the newer 3.5 Haiku).

---

## 2. LLM Integration Quality Assessment

### 2.1 Haiku Classification (Oversight Events)

**File**: `src/oversight/pipeline/classifier.py:45-78`
**Model**: `claude-3-5-haiku-20241022`

Two prompts are used sequentially:

**VA Relevance Prompt** (lines 45-60): Well-structured binary classifier with clear positive/negative examples. JSON-only output format is good for parsing reliability. Content truncated at 1000 chars -- adequate for classification but may miss relevant details in longer documents.

**Dated Action Prompt** (lines 63-78): Distinguishes current events from historical/evergreen content. This is a critical filter for noise reduction -- without it, the system would surface background articles alongside breaking developments.

**Assessment: 8/10**

Strengths:
- Clear, specific criteria in both prompts
- Two-stage classification (relevance then timeliness) is architecturally sound
- Fail-open design (assumes relevant on error) is correct for a surveillance system -- better to over-report than miss a critical signal

Weaknesses:
- **No confidence calibration**: The prompts request boolean outputs but don't ask for confidence scores. A confidence field would enable downstream threshold tuning without re-prompting.
- **Content truncation at 1000 chars**: For GAO reports or CRS analyses with long abstracts, the most relevant content may appear after the first 1000 characters. Consider extracting the most relevant section rather than taking the first 1000 chars.
- **No few-shot examples**: Adding 2-3 examples of each class (relevant/not, dated/not) would improve boundary-case accuracy.

### 2.2 Haiku Classification (State Intelligence)

**File**: `src/state/classify.py:174-185`
**Model**: `claude-3-haiku-20240307` (LEGACY)

**Critical Finding**: State intelligence uses the **legacy Haiku model** (`HAIKU_LEGACY_MODEL`) while oversight uses the newer 3.5 Haiku. From `src/llm_config.py:12`:

```python
HAIKU_LEGACY_MODEL = "claude-3-haiku-20240307"
```

The state classification prompt is more sophisticated than the oversight prompt -- it asks three questions (specific event? federal program? severity?) and returns structured JSON with reasoning. This is good prompt engineering.

**Assessment: 7/10**

Strengths:
- Multi-question prompt structure forces the LLM to consider multiple dimensions
- Explicit noise filtering ("is this a specific, dated event?")
- Program detection (PACT Act, Community Care, VHA) is domain-specific and valuable
- Fallback to keyword classification on LLM error is a sound resilience pattern

Weaknesses:
- **Legacy model should be upgraded to 3.5 Haiku** -- the newer model is faster, cheaper, and more accurate
- **No system prompt**: Unlike the oversight classifier, the state classifier sends only a user message. A system prompt would improve consistency.
- **JSON extraction via string slicing** (lines 209-215): `text.find("{")` is fragile. The oversight classifier uses `json.loads()` directly on the response, which is cleaner.

### 2.3 Sonnet Deviation Detection (Oversight)

**File**: `src/oversight/pipeline/deviation.py:30-54`
**Model**: `claude-sonnet-4-20250514`

The Sonnet deviation prompt is well-designed with a clear taxonomy:
- `new_topic`, `frequency_spike`, `tone_shift`, `escalation`, `unprecedented`

And explicit not-deviations:
- Routine periodic reports, continuation of existing investigations, standard administrative actions

**Assessment: 8/10**

Strengths:
- Conservative bias ("only flag true deviations that would be newsworthy") is correct for a high-signal system
- Confidence score (0-1) enables downstream filtering
- Baseline context includes event count, summary, and topic distribution
- Fail-closed design (returns `is_deviation=False` on error) prevents false positives

Weaknesses:
- **Content truncated at 1500 chars** (line 87) -- same concern as the classifier
- **No chain-of-thought**: The prompt asks for direct classification. Adding "think step by step" or a brief reasoning field would improve accuracy on ambiguous cases.
- **Topic distribution in baseline is keyword-based** (see Section 4 below) -- feeding keyword-frequency data to an LLM is suboptimal. The LLM would benefit more from example event titles/summaries.

### 2.4 Sonnet Agenda Drift Explanation

**File**: `src/agenda_drift.py:215-226`
**Model**: `claude-sonnet-4-20250514`

The deviation explanation prompt is well-constrained:
- 1-2 sentence limit prevents verbose outputs
- Explicit guidelines (focus on topic/framing shift, not quality; be factual; be neutral)
- Provides 3-5 typical utterances for comparison -- this is good few-shot grounding

**Assessment: 9/10**

This is the best-engineered prompt in the system. The typical-vs-flagged comparison structure is a pattern that should be replicated in other LLM calls.

---

## 3. Statistical Assessment of Deviation Detection

### 3.1 Agenda Drift Detection

**File**: `src/agenda_drift.py:24-28`

```python
DEVIATION_THRESHOLD_DIST = 0.20   # Minimum cosine distance to flag
DEVIATION_THRESHOLD_Z = 2.0       # Minimum z-score to flag
DEBOUNCE_K = 3                    # K of M utterances must exceed
DEBOUNCE_M = 8                    # Window size
```

#### Z-Score Threshold Analysis

**Is 2.0 sigma right?**

For normally distributed data, z >= 2.0 captures the top 2.28% of observations. However, cosine distances from a centroid in high-dimensional embedding space are **not normally distributed** -- they tend to follow a **right-skewed** distribution (most utterances cluster near the centroid with a long tail of outliers).

**Statistical concerns**:

1. **Distribution assumption**: Z-scores assume the underlying distribution is approximately normal. Cosine distances from a centroid typically follow a Beta or chi-squared-like distribution. Using z-scores on non-normal data will produce **miscalibrated** false-positive rates -- the actual false-positive rate could be significantly different from the expected 2.28%.

2. **Sample size sensitivity**: The minimum baseline requires only 5 embeddings (`MIN_EMBEDDINGS_FOR_BASELINE = 5` at `src/run_agenda_drift.py:17`). With n=5, the sample standard deviation is highly unstable. The `_std_dev` function correctly uses Bessel's correction (dividing by n-1), but with n=5 the confidence interval on sigma is extremely wide.

3. **The dual-threshold design is actually clever**: Requiring BOTH `dist >= 0.20` AND `z >= 2.0` creates a conjunction filter that reduces false positives from either criterion alone. The absolute distance threshold (0.20) guards against the case where a very narrow baseline (small sigma) produces inflated z-scores from small absolute deviations.

4. **K-of-M debounce is excellent**: The 3-of-8 debounce (`check_debounce` at line 159) converts a point anomaly detector into a sustained-shift detector. This is the right approach for agenda drift -- a single surprising utterance is noise; three in eight is a pattern.

**Recommendation**: The 2.0 threshold is a reasonable starting point, but the system should log the actual distribution of z-scores to verify whether the false-positive rate matches expectations. If the distribution is significantly non-normal, consider:
- Using percentile-based thresholds instead of z-scores (e.g., flag the top 5%)
- Applying a Box-Cox or log transformation before computing z-scores
- Or simply increasing the minimum baseline to n >= 20 to make the z-score approximation more reliable

#### Embedding Model Assessment

**File**: `src/embed_utterances.py:17`

```python
DEFAULT_MODEL = "all-MiniLM-L6-v2"  # 384 dimensions
```

This is a solid choice for the use case:
- 384 dimensions is compact enough for SQLite JSON storage
- MiniLM-L6-v2 is a well-validated model with good performance on semantic similarity tasks
- The model is local (no API calls), which is good for latency and cost

**Concern**: The model was trained primarily on English web text. Congressional hearing transcripts use specialized vocabulary (legal terms, policy jargon, committee-specific language). A domain-fine-tuned model or a larger model (e.g., `all-mpnet-base-v2`, 768 dimensions) might capture VA-specific semantic distinctions better. However, the improvement may be marginal for the drift detection use case where the signal is relative (deviation from personal baseline) rather than absolute.

### 3.2 Oversight Baseline / Deviation (Keyword-Based)

**File**: `src/oversight/pipeline/baseline.py:82-94`

The oversight baseline uses **keyword frequency counting** for topic distribution:

```python
topic_keywords = {
    "healthcare": ["healthcare", "health care", "medical", "hospital", "clinic"],
    "benefits": ["benefits", "compensation", "pension", "disability"],
    # ... 10 topic categories
}
```

**Assessment: 5/10**

This is the weakest analytical component in the pipeline. Issues:

1. **Only 10 topic categories** with 3-5 keywords each. This is a very coarse representation of the VA oversight landscape. Topics like "IT modernization," "PACT Act implementation," or "community care access" would be binned into broader categories or missed entirely.

2. **Normalization is sum-based** (line 107): `count / total` means topics with more keywords dominate. "healthcare" has 5 keywords; "housing" has 3. Healthcare will be systematically over-weighted.

3. **Only top 5 topics retained** (line 112): `topic_counts.most_common(5)` discards the long tail. If a source suddenly starts covering a niche topic, it won't appear in the baseline at all, making it invisible to the deviation detector.

4. **No temporal weighting**: All events in the 90-day window are weighted equally. Recent trends (last 2 weeks) should matter more than events from 80 days ago for deviation detection.

---

## 4. Oversight Escalation Logic -- Detailed Review

### 4.1 Escalation Signals

**File**: `src/oversight/db_helpers.py:277-344`

The system seeds 11 default escalation signals:

| Signal | Type | Severity |
|--------|------|----------|
| criminal referral | phrase | critical |
| subpoena | keyword | critical |
| emergency hearing | phrase | critical |
| arrest | keyword | critical |
| whistleblower | keyword | high |
| investigation launched | phrase | high |
| fraud | keyword | high |
| precedential opinion | phrase | high |
| first-ever | phrase | medium |
| reversal | keyword | medium |
| bipartisan letter | phrase | medium |

**Assessment: 7/10**

Strengths:
- Good severity stratification (4 critical, 4 high, 3 medium)
- Phrase matching for multi-word signals prevents false positives (e.g., "criminal referral" won't match "criminal" alone)
- Keyword matching uses word boundaries (`\b` regex) for single words

Weaknesses:
- **Missing high-value signals**: No patterns for "systemic failure," "data breach," "patient death/harm," "wait time crisis," "construction delay/overrun," "Secretary [testimony/resignation]"
- **No negative signals**: The system has no concept of "resolution" or "improvement" -- a "whistleblower vindicated" event would escalate the same as "whistleblower retaliation"
- **Static signal list**: Signals are seeded once and never updated. There's no mechanism to learn new escalation patterns from analyst feedback.

### 4.2 Priority Scoring

**File**: `src/oversight/pipeline/priority.py:33-36`

```python
_W_ML = 0.30         # ML score weight
_W_SIGNAL_COUNT = 0.25  # Number of escalation signals
_W_SEVERITY = 0.25      # Highest severity
_W_SOURCE = 0.20        # Source authority
```

**Assessment: 7/10**

The composite scoring is well-designed:
- Source authority weights are well-calibrated (OIG 0.90, GAO 0.85, trade_press 0.35)
- ML weight redistribution when ML is unavailable is correct
- Alert threshold (0.60) and WebSocket threshold (0.40) create a useful two-tier response

**Issue**: The `signal_count` component saturates at 5 (`min(count, 5) / 5.0`). An event matching 3 signals scores 0.60, while an event matching 10 signals scores only 1.0. The saturation point is reasonable, but the linear scaling within [0, 5] may under-weight events with 1-2 very high-severity signals vs. events with 4-5 medium-severity signals.

### 4.3 ML Scoring

**File**: `src/ml/scoring.py`

The `SignalScorer` is a **rule-based heuristic system** (not a trained ML model). It computes importance, impact, and urgency from:
- Keyword density
- Source reliability scores
- Regulation citation counts
- Temporal features (deadline proximity, effective date)
- Entity counts

**Assessment: 6/10**

This is adequate for a first-generation system, but calling it "ML scoring" is misleading -- it's a weighted rule ensemble. True ML scoring would use:
- Labeled training data from analyst-confirmed escalations
- A gradient-boosted classifier or logistic regression
- Cross-validation and calibration metrics

The current system's main value is providing an additional signal dimension beyond keyword matching, which is useful even without true ML.

---

## 5. Production Throughput Analysis

### 5.1 VNN Anchor Pack Pipeline

**Full path**: Source APIs -> Agents -> Quality Gate -> Dedup -> Escalation -> Deviation -> Storage -> Vigil Bridge (`~/.vigil/integrations/anchor_pack_generator.py`) -> YAML files

**Throughput Assessment for 2/week IRON COMPASS target**:

| Stage | Estimated Throughput | Bottleneck? |
|-------|---------------------|-------------|
| Source fetch (10 agents, parallel) | ~100 events/run | No |
| Quality gate | ~1ms/event | No |
| Deduplication | ~5ms/event (DB lookup) | No |
| Haiku classification | ~500ms/event (2 API calls) | **Moderate** |
| Escalation keyword check | ~1ms/event | No |
| Sonnet deviation check | ~2s/event | **Yes** |
| CEO Brief generation | ~30s/run (aggregation + LLM) | **Moderate** |
| Anchor pack generation | ~10ms/event | No |

**Key bottleneck**: Sonnet deviation detection at 2 seconds per event. For a run ingesting 50 new events, this adds ~100 seconds of sequential LLM calls. The system does have a heuristic pre-filter (`check_deviation_simple` at `deviation.py:158-197`) but it's not currently wired into the main pipeline flow in `runner.py`.

### 5.2 Can the Pipeline Sustain 2/Week VNN Packs?

**Yes, with caveats.**

The pipeline can produce 2 VNN packs per week if:

1. **Daily pipeline runs are maintained**: The system needs fresh data in the database. All 10 oversight agents run in parallel via `ThreadPoolExecutor` (`runner.py:294`), and state intelligence runs twice daily (morning/evening). This cadence is sufficient.

2. **CEO Brief runs weekly**: The brief pipeline (`ceo_brief/runner.py`) aggregates 7-day windows by default. Running it Monday and Thursday would produce 2 briefs per week.

3. **Anchor pack generation is triggered**: The `anchor_pack_generator.py` currently requires manual invocation or a cron trigger. It reads from `~/.vigil/data/queue.db`, which must be populated by the Vigil bridge. **This is the main gap** -- the bridge module syncs events to the queue, but there's no automated trigger to run the pack generator.

4. **Editorial review is factored in**: The anchor packs are marked `# Review required before production`. The 2/week target assumes human review time is available.

**Estimated end-to-end latency** (signal publication to VNN-ready pack):
- Automated: 1-4 hours (next scheduled pipeline run + classification + pack generation)
- With review: 4-24 hours (depends on human reviewer availability)

---

## 6. Cross-Source Correlation Quality

**File**: `src/signals/correlator.py`

The `CorrelationEngine` is a sophisticated compound threat detector that correlates events across 5 source types (oversight, bills, hearings, federal register, state). It uses:

- Declarative YAML rules with configurable temporal windows
- Topic keyword overlap detection
- Title similarity (Jaccard on word sets) as a fallback
- Severity multipliers for escalation bonus and source count bonus

**Assessment: 7/10**

Strengths:
- Pair-wise comparison across all available source types is thorough
- State divergence rule (N+ events from different states sharing a topic) is an original and valuable detection pattern
- Compound signal IDs are deterministic (SHA256 of rule + event IDs), preventing duplicate alerts

Weaknesses:
- **Topic overlap relies on only 6 keyword categories** (`TOPIC_KEYWORDS` at `correlator.py:22-29`): disability_benefits, rating, exam_quality, claims_backlog, appeals, vasrd. This is far too narrow -- a GAO healthcare report and a congressional hearing on healthcare would not correlate because "healthcare" is not in the keyword vocabulary.
- **Title similarity threshold (0.85)** is very high. Most correlated events will have different titles. Consider lowering to 0.5-0.6 or using TF-IDF similarity.
- **No temporal weighting**: Events from 168 hours ago are treated the same as events from 1 hour ago within the correlation window.

---

## 7. Top 5 Analytical Improvements Ranked by Veteran Impact

### #1: Upgrade State Classification Model (HIGH IMPACT)
**File**: `src/llm_config.py:12` and `src/state/classify.py:8`
**Current**: `claude-3-haiku-20240307` (legacy, slower, less accurate)
**Recommended**: `claude-3-5-haiku-20241022` (already used for oversight)

State intelligence directly monitors veteran services across 10 states. Misclassification at this level means a veteran-harming program disruption in Texas could be rated "low" instead of "high." This is a single-line change with outsized impact:

```python
# src/state/classify.py:8
# Change: from src.llm_config import HAIKU_LEGACY_MODEL as HAIKU_MODEL
# To:     from src.llm_config import HAIKU_MODEL
```

**Veteran impact**: Faster, more accurate detection of state-level disruptions to VA services (PACT Act implementation delays, Community Care access issues, facility closures).

### #2: Expand Correlation Topic Vocabulary (HIGH IMPACT)
**Files**: `src/signals/correlator.py:22-29`, `src/oversight/pipeline/baseline.py:83-94`

The correlation engine and baseline builder share an impoverished topic vocabulary. Expanding from 6/10 categories to 20+ categories (healthcare, mental_health, technology, staffing, PACT_Act, community_care, EHR_modernization, facility_construction, toxic_exposure, homelessness, education, employment, caregiver, women_veterans, rural_access, telehealth, pharmacy, dental, vision, long_term_care) would dramatically improve:

- Cross-source correlation hit rate
- Deviation detection sensitivity
- CEO brief topic classification accuracy

**Veteran impact**: Compound threats that span multiple sources (e.g., OIG report on EHR + congressional hearing on EHR + news coverage) would be detected and escalated as a unified pattern instead of three unrelated events.

### #3: Add Confidence Calibration to LLM Classifiers (MEDIUM IMPACT)
**Files**: `src/oversight/pipeline/classifier.py:45-78`, `src/state/classify.py:174-185`

Add confidence scores to both classification prompts:
```json
{"is_va_relevant": true, "confidence": 0.92, "explanation": "..."}
```

Then implement threshold-based routing:
- Confidence >= 0.8: Auto-accept/reject
- Confidence 0.5-0.8: Flag for human review
- Confidence < 0.5: Apply secondary classifier

**Veteran impact**: Reduces both false positives (wasted analyst time reviewing irrelevant signals) and false negatives (missed signals that affect veterans). Creates a principled human-in-the-loop triage system.

### #4: Implement Baseline Temporal Decay (MEDIUM IMPACT)
**File**: `src/oversight/pipeline/baseline.py:135-183`

Replace the flat 90-day window with exponential temporal weighting:

```
weight(event) = exp(-lambda * days_old)
```

Where `lambda` controls the decay rate (e.g., lambda=0.02 gives a half-life of ~35 days).

This means recent patterns (last 2-3 weeks) dominate the baseline, making the deviation detector more responsive to genuine shifts while still maintaining memory of older patterns.

**Veteran impact**: Faster detection of emerging oversight patterns. If VA OIG suddenly increases attention to a topic that was quiet 60 days ago, the current system treats it as normal because it's within the flat 90-day window. Temporal decay would flag it as a deviation.

### #5: Wire Heuristic Pre-Filter for Sonnet Deviation (LOW-MEDIUM IMPACT)
**Files**: `src/oversight/pipeline/deviation.py:158-197`, `src/oversight/runner.py:108-176`

The `check_deviation_simple()` function exists but is not called in the main pipeline. Wiring it as a pre-filter before the Sonnet call would:
- Reduce Sonnet API calls by an estimated 60-80% (most events match baseline patterns)
- Cut pipeline latency from ~100s to ~30s for a typical 50-event run
- Reduce API costs proportionally

Pipeline change: Only call Sonnet `check_deviation()` if `check_deviation_simple()` returns `is_deviation=True` OR the event matches escalation signals.

**Veteran impact**: Faster pipeline = faster alerts. For time-critical signals (emergency hearing, facility closure), reducing end-to-end latency from 4 hours to 1 hour could enable same-day VNN coverage.

---

## 8. Specific Code Issues and File References

### Issue 1: Quality Gate Dead Code
**File**: `src/oversight/pipeline/quality_gate.py:37-38`
```python
if timestamps.pub_precision == "unknown" and not timestamps.pub_timestamp:
```
The `not timestamps.pub_timestamp` check is redundant here -- if `pub_timestamp` is None, the function already returned on line 31. This branch is dead code.

### Issue 2: Classifier Fail-Open vs Fail-Closed Inconsistency
- **Haiku classifier** (`classifier.py:98-99`): Fails **open** -- assumes relevant on error
- **Sonnet deviation** (`deviation.py:111-112`): Fails **closed** -- assumes no deviation on error

This is actually correct behavior (surveillance fail-open, escalation fail-closed), but it should be explicitly documented as a design decision.

### Issue 3: Oversized Agent Thread Pool
**File**: `src/oversight/runner.py:294`
```python
ThreadPoolExecutor(max_workers=len(AGENT_REGISTRY))
```
This creates 10 threads for 10 agents. Since all agents make HTTP requests to external APIs, this is I/O-bound and the thread count is fine. However, the rate limiter (`external_api_limiter.allow()` in each agent) is a shared singleton -- verify it's thread-safe.

### Issue 4: State Runner Has Inline DB Update
**File**: `src/state/runner.py:271-281`
The `_process_single_state` function imports `db.connect` and `db.execute` inline to update the program field. This breaks the clean separation where all DB operations go through `db_helpers.py`. Should be refactored into a `update_signal_program(signal_id, program)` helper.

### Issue 5: Anchor Pack Generator Uses Separate SQLite DB
**File**: `~/.vigil/integrations/anchor_pack_generator.py:23`
```python
VIGIL_QUEUE_DB = Path.home() / ".vigil" / "data" / "queue.db"
```
The pack generator reads from Vigil's `queue.db`, not from VA Signals' `signals.db`. This means the bridge module must sync events between databases. Any sync failure silently prevents pack generation. Consider adding a health check that verifies queue.db has recent entries.

---

## 9. Summary Assessment

**Overall Pipeline Quality: 7.2/10**

The intelligence pipeline is a production-grade system with strong architectural foundations:
- Clear source -> gate -> dedup -> classify -> escalate -> route -> produce flow
- Multi-model LLM integration (Haiku for filtering, Sonnet for analysis)
- Cross-source correlation for compound threat detection
- Two independent deviation detection systems (embedding-based for rhetoric, LLM-based for oversight)
- Full provenance chain from raw source to CEO brief

**Strengths**: Source diversity (30+), parallel agent execution, fail-closed escalation, dual-model LLM architecture, cross-command CEO brief integration (BRAVO/CHARLIE/DELTA)

**Weaknesses**: Narrow topic vocabularies, legacy model for state classification, missing heuristic pre-filter, keyword-based baseline topics feeding into LLM prompts, limited escalation signal vocabulary

**For IRON COMPASS 2/week VNN production**: Achievable with current architecture. The main gap is automated triggering of the anchor pack generator from the Vigil bridge. The pipeline can process signals in 1-4 hours; editorial review is the actual pacing constraint.
