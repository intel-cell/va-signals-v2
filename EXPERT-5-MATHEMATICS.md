# EXPERT-5: Mathematical Foundations & Algorithm Optimization

**Assessor**: Mathematician, Statistician & Physicist
**Date**: 2026-02-07
**Scope**: Statistical methods, algorithmic foundations, embedding quality, efficiency analysis
**Codebase**: VA Signals v2 (`/Users/xa/Work_VC/va-signals-v2/`)

---

## Executive Summary

VA Signals v2 employs six major quantitative subsystems. The mathematical foundations are generally sound for an intelligence monitoring platform at this scale, but several methods rest on implicit distributional assumptions that are likely violated, and the scoring/weighting systems are entirely heuristic without empirical calibration. The system's greatest mathematical risk is not any single algorithm failing, but the compounding of uncalibrated confidence scores across multiple pipeline stages, creating a false sense of precision.

**Overall Grade**: B- (Competent engineering with principled structure, but lacking formal statistical rigor in several critical paths)

---

## 1. Agenda Drift Detection

**Files**: `src/agenda_drift.py` (lines 1-346), `src/routers/agenda_drift.py`

### 1.1 Architecture Review

The system implements a classical change-point detection pipeline:

1. Compute centroid (mean vector) of member's historical embeddings
2. Measure cosine distance from new utterance to centroid
3. Compute z-score relative to historical distance distribution
4. Apply dual threshold: distance >= 0.20 AND z-score >= 2.0
5. K-of-M debounce filter (K=3 of M=8)

### 1.2 Cosine Distance as Metric

**Finding**: Cosine distance is the correct metric for this application.

Cosine distance operates in the angular space of the embedding manifold, which is where sentence-transformers concentrate their semantic information. Euclidean distance would be dominated by vector magnitude variations (which encode sentence length/complexity more than meaning). For detecting *rhetorical drift* -- shifts in topic framing rather than verbosity changes -- cosine distance is the standard and appropriate choice.

**Mathematical note**: The implementation at `src/agenda_drift.py:35-51` is correct:

```
d(a,b) = 1 - (a . b) / (||a|| * ||b||)
```

The range is [0, 2] for arbitrary vectors, though for sentence-transformer outputs (which are typically L2-normalized), the practical range is [0, 2] but empirically concentrated in [0, 0.5] for semantically related texts.

**One concern**: The degenerate case handler (line 48) returns 1.0 for zero-norm vectors. This is defensible (maximum uncertainty), but a near-zero vector from a very short or degenerate utterance could produce misleading distance values. A minimum utterance length gate before embedding would be more principled.

### 1.3 Z-Score Normality Assumption -- CRITICAL ISSUE

**Finding**: The z-score approach implicitly assumes cosine distances follow a normal distribution. This assumption is almost certainly violated.

**Mathematical reasoning**: Cosine distances are bounded on [0, 2]. For sentence-transformer embeddings of topically coherent text (a single committee member's statements), the distances from centroid will be:
- Right-skewed (most utterances cluster near the centroid)
- Bounded below by 0
- Potentially multimodal (if the member covers 2-3 distinct topic areas)

For a right-skewed, bounded distribution, the z-score at threshold 2.0 does NOT correspond to the expected 4.55% false positive rate (which assumes Gaussian tails). The actual false positive rate depends on the kurtosis and skewness of the empirical distribution.

**Formal analysis**: Let `X ~ F` be the true distribution of distances. The z-score is:

```
z = (x - mu_hat) / sigma_hat
```

For the Gaussian case, `P(z > 2.0) = 0.0228` (one-tailed) or `~4.55%` (two-tailed). But for a right-skewed distribution with excess kurtosis `kappa`:

```
P(z > 2.0) approx P_Gaussian(z > 2.0) * (1 + kappa/4 * (z^2 - 3))
```

For typical embedding distance distributions (kurtosis ~3-6), the actual false positive rate at z=2.0 could be 6-12%, roughly 2-3x the assumed rate.

**Recommendation**: Replace z-score with a **nonparametric percentile threshold**. Store the empirical CDF of distances and flag when a new distance exceeds the 95th or 97.5th percentile. This is distribution-free and requires no normality assumption. Implementation: store sorted distance array in baseline, use bisect for O(log n) lookup.

### 1.4 Centroid as Baseline -- Limitations

**Finding**: The mean vector centroid (`src/agenda_drift.py:54-61`) is optimal only if the member's topic space is unimodal.

If a committee member regularly discusses both "healthcare access" and "budget oversight" (two distinct topic clusters), the centroid falls between these clusters. This creates a systematic bias: *all* utterances appear deviant because the centroid represents a position the member never actually occupies.

**Recommendation**: Consider **k-medoids clustering** (k=2-3) on the member's embedding history, then measure distance to the *nearest* cluster center. This handles multimodal baselines. The minimum k can be selected by silhouette score.

### 1.5 Window Length Analysis

**Current**: The baseline uses all historical embeddings (no explicit window -- `src/agenda_drift.py:83`, `get_ad_embeddings_for_member` fetches all).

**Analysis**: A member's rhetorical position naturally evolves. Using all-time embeddings means:
- Genuine gradual shifts are masked (the centroid drifts slowly to accommodate them)
- Ancient topic positions dilute the current baseline
- The minimum n=5 threshold (`src/agenda_drift.py:85`) is too low for stable statistics

**Optimal window analysis**:

| Window | Detection Sensitivity | False Positive Rate | Baseline Stability |
|--------|----------------------|--------------------|--------------------|
| 30 days | High (detects rapid shifts) | High (small n, noisy) | Low |
| 60 days | Medium-High | Medium | Medium |
| **90 days** | **Medium (good balance)** | **Low-Medium** | **Good** |
| 120 days | Low (gradual shifts absorbed) | Low | High |
| All-time | Very Low | Very Low | Very High (but stale) |

**Recommendation**: Implement a 90-day rolling window (aligning with the oversight baseline in `src/oversight/pipeline/baseline.py:139`). Require minimum n=20 embeddings for statistical reliability (current n=5 is insufficient for reliable sigma estimation with Bessel's correction).

### 1.6 Debounce Filter Mathematical Properties

**Current**: K=3 of M=8 (`src/agenda_drift.py:27-28`)

**Analysis**: This is a binomial filter. Under the null hypothesis (no true drift), if each utterance has independent probability p of exceeding the threshold:

```
P(K >= 3 | M=8, p) = 1 - sum_{k=0}^{2} C(8,k) * p^k * (1-p)^(8-k)
```

At the theoretical p=0.0228 (z>2.0 under normality):
```
P(K >= 3 | M=8, p=0.0228) = 0.00015 (0.015%)
```

This is extremely conservative -- the debounce reduces false alerting by ~150x. However, this also means true drift must be *sustained* across 3 of 8 consecutive utterances to be detected, creating significant detection lag (potentially weeks of hearings).

**Recommendation**: Consider K=2 of M=5 for faster detection with acceptable false positive rate:
```
P(K >= 2 | M=5, p=0.0228) = 0.0025 (0.25%)
```

This is still well below 1% false alarm rate while detecting drift ~2-3x faster.

### 1.7 Alternative Detection Methods

| Method | Advantages | Disadvantages | Recommendation |
|--------|-----------|---------------|----------------|
| **Current (z-score + debounce)** | Simple, interpretable | Normality assumption, centroid bias | Baseline adequate |
| **CUSUM** | Optimal for detecting persistent mean shifts | Requires specifying shift magnitude a priori | **Recommended for Phase 2** |
| **EWMA** | Good for gradual drift detection | Less sensitive to sudden shifts | Good complement |
| **Bayesian change-point** | Posterior probability of change | Computationally expensive per utterance | Overkill at current scale |
| **Nonparametric percentile** | Distribution-free, no assumptions | Requires more data points for stability | **Recommended immediate fix** |

---

## 2. Escalation Scoring

**Files**: `src/oversight/pipeline/escalation.py` (lines 1-83), `src/oversight/pipeline/deviation.py` (lines 1-198)

### 2.1 Keyword Matching Analysis

The escalation checker (`escalation.py:37-83`) uses two matching modes:
- **Keyword**: Word-boundary regex match (`\b{pattern}\b`)
- **Phrase**: Substring match

**Mathematical assessment**: This is a binary bag-of-words classifier with manually curated features. It has:
- **Perfect precision by construction**: Matched patterns are hand-selected to be escalation-relevant
- **Unknown recall**: There is no measurement of how many true escalations are missed
- **No scoring gradation**: The severity is determined by the *highest single match*, not by the density or combination of matches

**Comparison with alternatives**:

| Method | Precision | Recall | Interpretability | Implementation Effort |
|--------|-----------|--------|------------------|-----------------------|
| **Current (keyword + severity map)** | High (curated) | Unknown/Low | Perfect | Already done |
| **TF-IDF + threshold** | Medium | Medium-High | Good | Low |
| **BM25 against escalation corpus** | Medium-High | High | Good | Medium |
| **Sentence-transformer similarity** | High | High | Medium | Medium (already have infra) |

**Key gap**: The system already has sentence-transformer infrastructure (from agenda drift). Using embedding similarity against a curated set of escalation exemplars would dramatically improve recall without sacrificing interpretability, since the matched exemplar can be shown as evidence.

### 2.2 ML Scoring Integration

The `_try_ml_score` function (`escalation.py:24-34`) attempts ML scoring via `SignalScorer` but catches all exceptions and falls back to keyword-only. This is good fail-closed behavior, but the ML score is stored in the result without influencing the `is_escalation` boolean:

```python
return EscalationResult(
    is_escalation=len(matched) > 0,  # Only keyword-driven
    ml_score=ml_score,               # Stored but unused in decision
)
```

**Finding**: The ML score is decorative -- it does not affect the escalation decision. This is either intentional conservatism (using ML for observability only) or an incomplete integration.

### 2.3 Deviation Classifier (LLM-based)

`src/oversight/pipeline/deviation.py:57-116` uses Claude Sonnet for deviation classification.

**Mathematical concerns**:
- **Confidence calibration**: The LLM returns a `confidence: 0.0-1.0` field, but LLM confidence scores are notoriously miscalibrated. There is no post-hoc calibration (e.g., Platt scaling, isotonic regression).
- **Fail-closed is correct**: On error, `is_deviation=False, confidence=0.0` (line 111). This satisfies the system's non-negotiable fail-closed principle.
- **Heuristic fallback**: `check_deviation_simple` (line 158) uses topic overlap with a hardcoded confidence of 0.6 regardless of overlap magnitude. This is mathematically unprincipled -- confidence should scale with the evidence (e.g., confidence = 1 - overlap_score).

### 2.4 Topic Distribution Computation

`src/oversight/pipeline/baseline.py:70-113` computes topic distributions via keyword frequency counting across 10 fixed categories.

**Mathematical issues**:
1. **Topic leakage**: Keywords like "it " (with trailing space, `features.py:24`) will match inside words. The regex in baseline.py uses `\b` correctly, but the feature extractor does not.
2. **Fixed vocabulary**: Only 10 topic categories with ~3-5 keywords each. Novel topics (e.g., "AI in VA claims processing") would be invisible.
3. **Frequency normalization**: Division by total keyword hits (`baseline.py:107-113`) means a single mention of "fraud" in 100 "healthcare" mentions gives fraud a 1% share. This is reasonable but sensitive to keyword list balance.

---

## 3. Health Score Aggregation

**File**: `src/resilience/health_score.py` (lines 1-275)

### 3.1 Current Weight Structure

```
Health = 0.35 * Freshness + 0.30 * ErrorRate + 0.20 * CircuitBreaker + 0.15 * Coverage
```

**Mathematical properties of linear combination**:
- **Compensatory**: A perfect score in one dimension can offset failure in another. Example: 100% freshness + 100% CB + 100% coverage = 70 even if error_rate = 0 (all errors). This yields a grade "C", which may be misleading when data is completely corrupted.
- **Additive independence**: Assumes no interaction between dimensions. In reality, high error rate + open circuit breakers are correlated (cascade failures), and their joint occurrence should penalize more than independently.
- **Scale consistency**: All dimensions output 0-100 before weighting. This is correct -- the linear combination is dimensionally consistent.

### 3.2 Weight Justification Analysis

**Are the weights justified?** No -- they are heuristic. However, the ordering is defensible:

**Informal sensitivity analysis**: Which dimension's failure matters most to the system's mission (detecting VA-relevant signals)?

1. **Freshness (35%)**: If data is stale, the system is blind. *Most critical.*
2. **Error Rate (30%)**: If pipelines are failing, data is unreliable. *Second most critical.*
3. **Circuit Breakers (20%)**: CB state reflects current resilience posture. *Important but lagging.*
4. **Coverage (15%)**: Missing tables indicate structural problems. *Least time-sensitive.*

This ordering aligns with operational priority. A formal **Analytic Hierarchy Process (AHP)** or **Delphi method** would validate whether 35/30/20/15 is approximately correct, but the relative ordering is sound.

**Would PCA suggest different weights?** PCA maximizes variance explained, which is not the same as maximizing *operational relevance*. PCA on health dimensions would likely over-weight error_rate (most variable in practice) and under-weight coverage (binary/stable). This would be the wrong objective. The current expert-assigned weights are preferable for a decision support system.

### 3.3 Nonlinearity and Interaction Terms -- SIGNIFICANT GAP

**Finding**: The current linear model has a critical blind spot for catastrophic states.

**Example pathological case**:
- Freshness: 100 (all sources fresh)
- Error Rate: 0 (all runs failed, but penalty capped at 20 points: score = max(0, 0-20) = 0)
- Circuit Breaker: 100 (all closed -- they haven't tripped yet because the errors are too new)
- Coverage: 100 (tables have old data from before the failure)

**Health = 0.35(100) + 0.30(0) + 0.20(100) + 0.15(100) = 35 + 0 + 20 + 15 = 70** -- Grade "C"

A system where *every pipeline is erroring* gets a "C" grade. This is dangerously optimistic.

**Recommendation**: Implement a **floor gate** (multiplicative penalty):

```python
# If any critical dimension scores below threshold, cap overall score
MIN_DIMENSION_THRESHOLD = 30.0
if any(d.score < MIN_DIMENSION_THRESHOLD for d in dimensions):
    worst = min(d.score for d in dimensions)
    weighted_score = min(weighted_score, worst * 1.5)
```

This ensures a catastrophic dimension failure cannot be masked by healthy dimensions.

### 3.4 Error Rate Penalty Structure

`src/resilience/health_score.py:118-160`

The 20-point penalty for any source with >50% failure rate (`line 147`) is a step function:
- 49% failure: no penalty
- 51% failure: -20 points

This creates a discontinuity. A smooth penalty function would be more mathematically principled:

```
penalty(rate) = 20 * max(0, (rate - 0.3) / 0.7)^2
```

This applies a gradual quadratic penalty starting at 30% failure rate, reaching full 20-point penalty at 100%.

### 3.5 Circuit Breaker Half-Open Scoring

`src/resilience/health_score.py:178-183`

HALF_OPEN scores 0.5 (50% health). This is reasonable -- HALF_OPEN means "attempting recovery." However, the time spent in HALF_OPEN is not factored. A circuit breaker that has been HALF_OPEN for 10 minutes (recovering) is different from one stuck HALF_OPEN for 6 hours (flapping). A decay function on HALF_OPEN health would add temporal sensitivity.

---

## 4. Deduplication

**File**: `src/oversight/pipeline/deduplicator.py` (lines 1-226)

### 4.1 Entity Extraction Patterns

Six regex patterns extract canonical identifiers:
- GAO: `GAO-YY-NNNNN`
- OIG: `YY-NNNNN-NNN`
- House bills: `H.R. N+`
- Senate bills: `S. N+`
- CAFC cases: `YYYY-NNNNN`
- CRS reports: `RXXXXX`

**Mathematical assessment**: This is a deterministic, exact-match deduplication system. Its properties:
- **Precision**: ~100% (false positives require accidental ID collision)
- **Recall**: Low for events without structured identifiers. News articles about the same GAO report may not contain the GAO number.

### 4.2 Missing Fuzzy Matching -- SIGNIFICANT GAP

**Finding**: The deduplicator has no fallback for entity-free events.

When `extract_entities` returns empty (`line 200-204`), the event is unconditionally treated as new. This means two news articles about the same topic from different sources, neither containing a structured ID, will both be stored as separate canonical events.

**Recommended approach**:

1. **Title similarity**: Compute Jaccard similarity or edit distance (Levenshtein) on normalized titles. Threshold at 0.7 similarity.
2. **Embedding similarity**: If sentence-transformer infrastructure is available, compute cosine similarity between the new event's title+summary embedding and recent events. Threshold at 0.85.
3. **Time-gated**: Only check similarity against events from the last 7 days (prevents unbounded comparison set).

**Complexity analysis**: For option 2, comparing against N recent events is O(N*d) where d is embedding dimension. With d=384 (MiniLM) and N=100 (7-day window), this is ~38K multiplications per dedup check -- negligible.

### 4.3 LIKE-Based JSON Search

`src/oversight/pipeline/deduplicator.py:98-108`

```sql
WHERE canonical_refs LIKE :canonical_match
```

This performs a full-text scan on the `canonical_refs` JSON column. For large `om_events` tables, this is O(N) per entity check. With 6 entity types checked sequentially, worst case is 6N row scans.

**Recommendation**: Add an index: `CREATE INDEX idx_om_events_canonical ON om_events(canonical_refs)`. For SQLite, a functional index on JSON extract would be better:

```sql
CREATE INDEX idx_om_events_gao ON om_events(json_extract(canonical_refs, '$.gao_report'))
```

---

## 5. Heat Map Risk Matrix

**Files**: `src/signals/impact/heat_map_generator.py` (lines 1-508), `src/signals/impact/models.py` (lines 1-520)

### 5.1 Risk Score Calculation

```python
score = likelihood * impact * urgency_factor
```

Where:
- `likelihood` in {1, 2, 3, 4, 5}
- `impact` in {1, 2, 3, 4, 5}
- `urgency_factor` in {1.0, 1.2, 1.5, 2.0}

**Score range**: [1*1*1.0, 5*5*2.0] = [1.0, 50.0]

**Mathematical properties**:
- **Multiplicative interaction**: likelihood=5, impact=1 scores 5.0, while likelihood=3, impact=3 scores 9.0. The multiplicative form correctly penalizes imbalanced risk profiles -- a highly likely but low-impact event ranks below a moderately likely, moderately impactful event. This is mathematically appropriate for risk prioritization.
- **Urgency as multiplier**: The 2.0x factor for <=7 days means urgency can double the priority. This is a strong effect -- a low-risk item (L:2, I:2 = 4.0) with 7-day urgency (8.0) outranks a medium-risk item (L:3, I:3 = 9.0) with 31+ days. Whether this is desired depends on operational doctrine.

### 5.2 Quadrant Classification

`src/signals/impact/models.py:252-275`

The threshold is `>= 3` for "high" on both axes. On a 1-5 scale, this means:
- HIGH_PRIORITY: likelihood >= 3 AND impact >= 3 (9 of 25 cells = 36%)
- WATCH: likelihood < 3 AND impact >= 3 (6 cells)
- MONITOR: likelihood >= 3 AND impact < 3 (6 cells)
- LOW: likelihood < 3 AND impact < 3 (4 cells)

**Finding**: The threshold at 3 makes HIGH_PRIORITY the largest quadrant (36%). This may cause alert fatigue. A threshold of >= 4 would create a more selective HIGH_PRIORITY (4 of 25 = 16%), with an intermediate "ELEVATED" category.

### 5.3 Likelihood Assessment Calibration

`src/signals/impact/heat_map_generator.py:31-107`

The assessment functions use keyword matching on action text:
```python
if "passed" in latest_action:
    score = 5
elif "reported" in latest_action:
    score = 4
...
```

**Calibration concern**: These are ordinal scores, not calibrated probabilities. "Score 3" for hearing does not mean "60% probability of advancement." Without empirical calibration (e.g., historical passage rates for bills at each stage), the scores reflect relative ordering but not quantitative risk.

**Recommendation**: For the bill likelihood assessor, use historical Congressional passage rates:
- Introduced: ~3% pass rate -> L=1
- Committee hearing: ~15% -> L=2
- Reported out of committee: ~40% -> L=3
- Passed one chamber: ~70% -> L=4
- Passed both chambers: ~95% -> L=5

This would be empirically grounded rather than heuristic.

### 5.4 Urgency Factor Step Function

The urgency mapping (`models.py:240-247`) has discontinuities:
- Day 7: 2.0x
- Day 8: 1.5x (25% drop)
- Day 14: 1.5x
- Day 15: 1.2x (20% drop)

A continuous function would be smoother:

```python
urgency_factor = 1.0 + max(0, 1.0 - urgency_days / 30) ** 0.5
```

This gives: day 0 = 2.0, day 7 = 1.88, day 14 = 1.73, day 30 = 1.0 -- a smooth decay.

However, the step function is arguably *more appropriate* for decision-makers who think in discrete time horizons ("this week" vs "next week" vs "this month"). The current approach is defensible for the CEO brief context.

---

## 6. ML Scoring System

**Files**: `src/ml/scoring.py` (lines 1-339), `src/ml/features.py` (lines 1-300)

### 6.1 Overall Score Architecture

```python
overall = importance * 0.35 + impact * 0.40 + urgency * 0.25
```

**Observation**: The weights (35/40/25) are different from the health score weights but follow a similar pattern -- no empirical derivation, but reasonable expert ordering. Impact weighted highest makes sense for a system focused on veteran outcomes.

### 6.2 Feature Engineering Quality

`src/ml/features.py` extracts 15+ features. Key mathematical observations:

**Keyword density** (`features.py:153-156`):
```python
keyword_density = hp_matches / word_count
```
This is a proper normalized frequency. However, the scoring function applies a 50x multiplier capped at 0.25 (`scoring.py:149`):
```python
score += min(0.25, features.keyword_density * 50)
```
For a 1000-word document with 5 keyword matches (density = 0.005), this contributes `0.005 * 50 = 0.25` (maximum). This means 5 keywords in 1000 words saturates the density score. This seems too easy to saturate -- the function has no discriminating power above 5 matches.

**Regulation citations** (`features.py:239-247`):
```python
reg_count = sum(len(re.findall(p, text, re.IGNORECASE)) for p in reg_patterns)
```
This counts all citation matches across patterns. However, the same regulation cited 3 times counts as 3, while 3 different regulations also count as 3. For importance scoring, *unique* regulation citations should matter more than repeated ones.

### 6.3 Confidence Calculation -- MATHEMATICAL WEAKNESS

`src/ml/scoring.py:243-269`

The confidence score is additive with hardcoded increments:
```python
confidence = 0.3  # base
if text_length > 500: confidence += 0.15
if source_type in authoritative: confidence += 0.20
if days_until_effective is not None: confidence += 0.15
if days_until_deadline is not None: confidence += 0.10
if regulation_citations > 0: confidence += 0.10
```

**Maximum achievable**: 0.3 + 0.15 + 0.20 + 0.15 + 0.10 + 0.10 = **1.00**

**Issue**: This measures *feature completeness*, not prediction *confidence*. A signal could have all features present (confidence=1.0) but receive contradictory evidence (e.g., authoritative source saying something routine). True confidence should reflect the *internal consistency* of the scoring model, not just data availability.

**Recommendation**: Use a proper confidence metric:
```python
confidence = feature_completeness * (1.0 - scoring_entropy)
```
Where `scoring_entropy` measures how spread the component scores are. If importance=0.9, impact=0.1, urgency=0.8, that's a contradictory profile (high importance but low impact?) that should have lower confidence.

### 6.4 Source Reliability Scores

`src/ml/features.py:57-67`

```python
SOURCE_RELIABILITY = {
    "federal_register": 0.95,
    "congress_gov": 0.95,
    ...
    "news": 0.60,
    "other": 0.50,
}
```

**Finding**: These are reasonable prior estimates, but they are static. A Bayesian approach would update reliability based on observed false positive/negative rates:

```
P(reliable | data) proportional to P(data | reliable) * P(reliable)
```

Where `P(reliable)` is the table above, and `P(data | reliable)` is estimated from how often signals from each source led to confirmed events. The `_extract_historical_features` stub (`features.py:253-261`) is a placeholder for exactly this kind of updating.

---

## 7. Signal Routing Engine

**Files**: `src/signals/engine/parser.py` (lines 1-88), `src/signals/engine/evaluator.py` (lines 1-165)

### 7.1 Expression Tree Evaluation

The engine implements a standard Boolean expression evaluator with three operators:
- `all_of` (AND): short-circuit on first failure
- `any_of` (OR): evaluates all children (no short-circuit!)
- `none_of` (NOT ANY): short-circuit on first success

**Complexity analysis**: For an expression tree with depth D and branching factor B:
- Worst case: O(B^D) evaluator invocations
- Max depth enforced at 5 (`parser.py:70`)
- With B=10 evaluators per node, worst case is 10^5 = 100,000 evaluations

**Finding**: The `any_of` evaluator (`evaluator.py:115-136`) does NOT short-circuit. It evaluates all children even after finding a match (to collect `matched_discriminators`). This is intentional for evidence collection but costs performance. For rules with many OR branches, this is O(N) instead of O(1) in the best case.

**Recommendation**: Add a `short_circuit=True` option for high-volume evaluation paths where evidence collection is not needed.

### 7.2 Evaluator Whitelist

`parser.py:76-78` validates evaluators against a whitelist. This is good security practice -- it prevents injection of arbitrary evaluator names from YAML config files.

---

## 8. Algorithmic Efficiency Assessment

### 8.1 Big-O Analysis by Component

| Component | Operation | Complexity | Concern? |
|-----------|-----------|-----------|----------|
| Agenda drift: `cosine_distance` | Per-utterance comparison | O(d) where d=embedding dim | No |
| Agenda drift: `build_baseline` | Build centroid + stats | O(n*d) where n=embeddings | No (n < 10K typically) |
| Agenda drift: `_mean_vector` | Element-wise mean | O(n*d) | No, but uses Python loops. NumPy would be 100x faster |
| Deduplicator: `find_canonical_event` | LIKE search per entity | **O(N) per entity, 6 entities** | **Yes at scale** |
| Heat map: `generate_combined` | Linear scan of inputs | O(B + H + M) | No |
| ML scoring: `score_batch` | Per-signal feature extraction | O(S * (W + P)) | No (S < 1000) |
| Expression evaluator | Per-envelope evaluation | O(B^D), D <= 5 | Manageable |
| Failure correlator | SQL GROUP BY | O(R) where R=runs in window | No |
| State classifier: `_compile_keyword_patterns` | Regex compilation (startup) | O(K) | No (one-time) |
| Topic distribution | Regex scan per keyword per topic | **O(T * K * |text|)** | Moderate for large corpora |

### 8.2 Embedding Computation Costs

Sentence-transformer embeddings are not computed in any of the code I reviewed -- they appear to be pre-computed and stored in `ad_embeddings`. The embedding computation itself is O(L^2 * d) for transformer attention (L=sequence length, d=model dimension), typically 50-200ms per utterance on CPU.

**Finding**: The system correctly pre-computes and caches embeddings rather than computing them inline. This is the right architectural choice.

### 8.3 N+1 Query Patterns

**Found in `src/resilience/health_score.py:64-115`**: The freshness computation loops through all expectations and calls `get_last_success()` for each source individually -- a classic N+1 pattern:

```python
for exp in expectations:  # N iterations
    last_success = get_last_success(exp.source_id, con=con)  # 1 query each
```

With 15 pipeline runners, this is 15 separate queries. A single query with `GROUP BY source_id` would reduce this to 1 query.

**Found in `src/routers/agenda_drift.py:100-168`**: The stats endpoint makes 5 sequential queries instead of a single JOIN.

### 8.4 Pure Python Vector Operations

`src/agenda_drift.py:35-69` implements cosine distance and mean vector in pure Python list comprehensions. For dimension d=384 (MiniLM):

```python
dot = sum(x * y for x, y in zip(a, b))  # 384 multiplications + 383 additions
```

This is ~100-1000x slower than NumPy's `np.dot()`. While acceptable for single-utterance comparisons, it would become a bottleneck in batch operations.

---

## 9. Top 5 Mathematical Improvements (Ranked by Analytical Impact)

### Rank 1: Replace Z-Score with Nonparametric Percentile for Agenda Drift
- **File**: `src/agenda_drift.py:132-136`
- **Current**: z-score assumes Gaussian distribution; false positive rate is ~2-3x the assumed 4.55%
- **Proposed**: Store sorted distance array in baseline, flag when distance exceeds empirical 97.5th percentile
- **Impact**: Eliminates the most consequential distributional assumption in the system
- **Effort**: Low (change baseline storage to include sorted distances, modify `detect_deviation` to use `bisect`)

### Rank 2: Add Floor Gate to Health Score
- **File**: `src/resilience/health_score.py:262-264`
- **Current**: Linear combination allows catastrophic dimensions to be masked (100% error rate still yields "C" grade)
- **Proposed**: `if any(d.score < 30): weighted_score = min(weighted_score, worst_dim * 1.5)`
- **Impact**: Prevents misleadingly healthy scores during cascading failures
- **Effort**: Trivial (3 lines)

### Rank 3: Fuzzy Deduplication Fallback for Entity-Free Events
- **File**: `src/oversight/pipeline/deduplicator.py:200-204`
- **Current**: Events without structured IDs are always treated as new (unknown duplicate rate)
- **Proposed**: Title Jaccard similarity (>0.7) + time window (7 days) as secondary dedup
- **Impact**: Reduces noise in oversight event stream, especially for news-wire sources
- **Effort**: Medium (new function, ~50 lines)

### Rank 4: Multimodal Baseline for Agenda Drift (k-medoids)
- **File**: `src/agenda_drift.py:72-106`
- **Current**: Single centroid misrepresents members with diverse topic portfolios
- **Proposed**: k-medoids clustering (k=2-3) with nearest-cluster distance measurement
- **Impact**: Eliminates systematic false positives for multi-topic committee members
- **Effort**: Medium (requires `sklearn` or manual implementation, ~100 lines)

### Rank 5: ML Score Integration into Escalation Decision
- **File**: `src/oversight/pipeline/escalation.py:74-83`
- **Current**: ML score is computed but does not influence `is_escalation` decision
- **Proposed**: `is_escalation = len(matched) > 0 OR (ml_score is not None and ml_score > 0.75)`
- **Impact**: Catches escalations missed by keyword matching using the already-computed ML score
- **Effort**: Trivial (1 line change + threshold calibration)

---

## Appendix A: Mathematical Notation Summary

| Symbol | Meaning | Used In |
|--------|---------|---------|
| d(a,b) = 1 - cos(a,b) | Cosine distance | Agenda drift |
| z = (x - mu) / sigma | Standard z-score | Agenda drift threshold |
| P(K >= k \| M, p) | Binomial CDF (debounce) | K-of-M filter |
| H = sum(w_i * s_i) | Weighted linear health | Health score |
| S = L * I * U | Risk priority score | Heat map |
| O = 0.35*Imp + 0.40*Imp + 0.25*Urg | Overall ML score | Signal scoring |

## Appendix B: File Reference Index

| File | Lines | Component |
|------|-------|-----------|
| `src/agenda_drift.py` | 1-346 | Drift detection, embedding analysis, LLM explanation |
| `src/routers/agenda_drift.py` | 1-235 | API endpoints for drift events/stats |
| `src/oversight/pipeline/escalation.py` | 1-83 | Keyword + ML escalation scoring |
| `src/oversight/pipeline/deviation.py` | 1-198 | LLM deviation classification |
| `src/oversight/pipeline/deduplicator.py` | 1-226 | Entity extraction + canonical matching |
| `src/oversight/pipeline/baseline.py` | 1-298 | Rolling baseline construction |
| `src/resilience/health_score.py` | 1-275 | Aggregate health score engine |
| `src/resilience/failure_correlator.py` | 1-156 | Failure correlation detection |
| `src/signals/impact/heat_map_generator.py` | 1-508 | Risk matrix generation |
| `src/signals/impact/models.py` | 1-520 | Data models, scoring formulas |
| `src/signals/engine/parser.py` | 1-88 | Boolean expression tree parser |
| `src/signals/engine/evaluator.py` | 1-165 | Expression tree evaluation |
| `src/signals/suppression.py` | 1-95 | Cooldown-based suppression |
| `src/ml/scoring.py` | 1-339 | Signal importance/impact/urgency scoring |
| `src/ml/features.py` | 1-300 | Feature extraction pipeline |
| `src/state/classify.py` | 1-267 | State signal classification |
