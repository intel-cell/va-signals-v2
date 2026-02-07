# EXPERT-4: Cognitive Architecture & Decision Quality Assessment

**Expert Domain:** Cognitive Science, Philosophy of Information, Human-AI Teaming
**Assessment Date:** 2026-02-07
**System Under Review:** VA Signals v2 + Vigil + VNN Pipeline

---

## 1. Decision Support Chain Analysis

### Signal-to-Decision Flow

The system implements a four-stage decision support chain:

```
Raw Sources → Aggregation → Analysis → Brief Generation → Commander Decision
   (30+)        (scored)      (ranked)     (formatted)       (human)
```

**Where signal degrades to noise:**

#### Stage 1 → 2: Aggregation (MODERATE DEGRADATION)

- `src/ceo_brief/aggregator.py:173-193` — Issue classification relies on regex keyword matching against 9 categories. This is brittle: a document about "VA staffing shortages impacting claims processing" could match STAFFING, BENEFITS_CLAIMS, or HEALTHCARE. The `max(scores, key=scores.get)` winner-take-all approach (line 193) discards multi-category relevance, forcing a single classification on inherently multi-dimensional signals.

- `aggregator.py:246-288` — Impact scoring uses fixed weights with no learning or calibration. The escalation flag gets 30% weight (`IMPACT_WEIGHTS["escalation"] = 0.3`), but a non-escalation final rule (impact 1.0 in ACTION_LEVELS) with high authority (0.9) can still outrank an actual escalation. The weights are reasonable but untested against ground truth.

- `aggregator.py:333-359` — Relevance scoring is a static lookup by issue area. Benefits/Claims = 1.0, Healthcare = 0.5. This means a critical healthcare signal (e.g., "VHA suspends C&P exams nationwide") scores 0.5 relevance while a routine claims notice scores 1.0. The scoring does not account for operational context.

#### Stage 2 → 3: Analysis (HIGH DEGRADATION RISK)

- `src/ceo_brief/analyst.py:170-215` — Message drafting uses template-based text generation with `_draft_message_from_delta()`. These are rule-generated talking points, NOT LLM-synthesized analysis. The "analyst" agent is entirely deterministic — no Claude/LLM call anywhere in the analyst pipeline. This is both a strength (reproducible, fast, no hallucination) and a critical weakness (no synthesis, no contextual judgment, no pattern recognition across signals).

- `analyst.py:464-471` — Stakeholder mapping is a static lookup table. The system has pre-defined stakeholders per issue area (lines 28-121) and maps them mechanically. It does not track evolving relationships, recent interactions, or which stakeholders are actually responsive. The Commander gets the same stakeholder list regardless of political context.

- `analyst.py:529-543` — Objection-response pairs are hardcoded templates (lines 124-155). These never update based on actual pushback received, shifts in political framing, or new counter-arguments entering the discourse.

#### Stage 3 → 4: Generation (LOW DEGRADATION)

- `src/ceo_brief/generator.py:142-227` — The generator faithfully assembles analyzed content. Signal preservation is high here. The main concern is the padding logic: when fewer than 3 messages, 5 stakeholders, or 3 objections exist, the system injects generic placeholder content (lines 158-208). A Commander receiving a brief with 2 real insights padded by "Continue monitoring policy developments" may not realize how thin the actual intelligence is. **The padding masks information scarcity.**

### Critical Finding: No LLM Anywhere in the CEO Brief Pipeline

The entire `ceo_brief/` pipeline — aggregation, analysis, generation — contains zero LLM calls. The "analyst" is pure heuristic. This means:
- No cross-signal synthesis ("These 3 bills + this FR rule + this hearing form a coordinated push on X")
- No contextual interpretation ("This low-scored signal matters because of the upcoming committee markup")
- No narrative construction (talking points are template fills, not crafted arguments)

The LLM calls are in the oversight pipeline (`oversight/pipeline/classifier.py`, `deviation.py`), which feeds upstream. But by the time signals reach the CEO Brief, they have been reduced to structured data and scored numerically. The "intelligence" in the intelligence brief is mechanical.

---

## 2. Standing Orders Compliance Audit

### SO#1: Seek Disconfirming Evidence

**Implementation:** PARTIALLY IMPLEMENTED

- **Briefing (human-written):** The 2026-02-06 briefing at `~/.vigil/briefings/2026-02-06.md` lines 57-60 explicitly flags "Claims of 57% backlog reduction are unverified by independent source. Warrants GAO/OIG data cross-check." Lines 110-111: "This is a Democratic minority report. Numbers should be triangulated with OIG/GAO data." This is SO#1 working correctly — but it is the *human analyst* (CDR Vigil via heartbeat pulse) doing this, not the automated pipeline.

- **CEO Brief pipeline:** `src/ceo_brief/analyst.py` does NOT seek disconfirming evidence. It ranks signals by impact score and presents the top N. If 5 signals all point the same direction, the brief will present a monoculture of perspective. There is no code that looks for signals contradicting the top-ranked ones.

- **Anchor packs:** `~/.vigil/integrations/anchor_pack_generator.py` generates packs with `risk_flags` (lines 79-81, 134-136, 201-203) that serve as minimal disclaimers ("Reports identify issues but do not guarantee fixes"), but these are generic templates, not evidence-specific disconfirmation.

**Gap:** Automated outputs never seek the opposing signal. The human briefing does; the machine does not.

### SO#2: Apply Source Hierarchy (Official > Verified > Secondary)

**Implementation:** IMPLEMENTED in scoring, NOT in presentation.

- `aggregator.py:159-170` — `SOURCE_AUTHORITY` dictionary implements the hierarchy: federal_register (0.9), oig (0.9), gao (0.85), bill (0.85), hearing (0.75), news (0.4). This correctly downweights secondary sources.

- `schema.py:60-73` — `SourceCitation` structure tracks source_type, source_id, url, date. Every claim can be traced.

- **But:** The CEO Brief markdown output (schema.py:263-371) does not visually distinguish source authority. A claim backed by a GAO report and a claim backed by a news wire appear identically. The Commander must mentally track which citations are high-authority.

- `anchor_pack_generator.py` uses confidence labels (VERIFIED, DEVELOPING) with rationale, which IS proper source hierarchy presentation.

**Gap:** Source hierarchy is computed but not surfaced in the CEO Brief's visual layout.

### SO#3: Flag Uncertainty Explicitly with Confidence Levels

**Implementation:** WEAKLY IMPLEMENTED

- `oversight/pipeline/deviation.py:14-21` — `DeviationResult` includes a `confidence: float` field (0-1). This is tracked in the pipeline.

- `oversight/pipeline/classifier.py:13-20` — `ClassificationResult` is binary (relevant/not, dated/not). No confidence gradient on the classification itself. Lines 97-102: on classification error, it defaults to "assume relevant" (fail-open), which is the correct resilience choice but it means uncertain items enter the pipeline *without being marked as uncertain*.

- **CEO Brief:** The `Likelihood` enum in `schema.py:29-34` is (HIGH, MEDIUM, LOW). This is used for risk assessment but not for *epistemic confidence* about the underlying facts. A signal can have HIGH impact but LOW confidence — and the schema does not model this distinction. The aggregator produces `impact_score`, `urgency_score`, `relevance_score` but no `confidence_score`.

- **Briefing (human-written):** The 2026-02-06 briefing uses "MEDIUM-HIGH" and "MEDIUM" source reliability ratings in a table (lines 98-108). This is excellent epistemic practice — and it is entirely manual.

**Gap:** The automated pipeline conflates impact with confidence. There is no `confidence_score` on aggregated deltas, and the CEO Brief schema has no field for epistemic uncertainty about facts (only about risk likelihood).

### SO#4: Note Who Benefits (Cui Bono)

**Implementation:** MANUAL ONLY

- **Briefing (human-written):** Line 112: "Cui bono: Democrats benefit politically from documenting VA failures under current administration. This does not invalidate the data — but it frames the presentation." This is textbook SO#4 execution.

- **CEO Brief pipeline:** Zero implementation. The analyst does not annotate signals with stakeholder interests. The `Stakeholder` dataclass (schema.py:90-102) has `why_they_care` but this describes their policy interest, not their self-interest in the specific signal. There is no "who benefits from this information being acted upon" analysis.

- **Anchor packs:** No cui bono analysis.

**Gap:** Entirely dependent on human analyst. No automated support.

### SO#5: No Narrative Lock-In

**Implementation:** STRUCTURAL RISK

- The `analyst.py` hardcoded templates create inherent narrative lock-in. Objection-response pairs (lines 124-155) present a fixed worldview. The risk assessments assume a specific posture (e.g., "Investing in veteran services is both a moral obligation and cost-effective" — line 137). These are reasonable positions, but they are not dynamic.

- The aggregator's `combined_score` (aggregator.py:473-474) creates a self-reinforcing ranking: once a category leads, signals in that category continue to dominate because `relevance_score` favors benefits/claims. The system has no mechanism for surfacing "the thing you're not paying attention to."

- **Briefing (human-written):** The updated assessment at line 152 demonstrates anti-lock-in: "The truth likely sits between: VA HAS reduced backlogs and improved some metrics, AND workforce losses ARE degrading care capacity." This explicitly holds competing hypotheses. The machine pipeline cannot do this.

**Gap:** Automated pipeline structurally locks into its initial categorization. No competing hypothesis generation.

---

## 3. CEO Brief Quality Assessment

### Strengths

1. **Schema design is excellent.** `schema.py` embodies the "CEO test" (lines 186-194): What do I say? To whom? When? What's the ask? This is the right framework for a decision instrument.

2. **Citation hard-gating.** Validation (schema.py:221-261) enforces every message must have supporting citations. Messages without citations generate validation errors. This is a strong provenance gate.

3. **Cross-command integration.** The `integrations.py` module pulls from BRAVO (evidence packs), CHARLIE (impact memos, heat maps, objections), and DELTA (decision points). When available, this enriches the brief significantly.

4. **Fail-closed validation.** BRAVO validation (`integrations.py:120-130`) returns `(False, ["unavailable"])` when the service is down — failing closed rather than passing unvalidated claims.

### Weaknesses

1. **Generic talking points.** Messages generated by `_draft_message_from_delta()` (analyst.py:170-215) follow templates like "VA just finalized new regulations on {topic}. We need to assess..." These are structurally correct but lack the rhetorical sharpness a CEO lobbyist needs. Compare to the human briefing's "57% backlog reduction claim appears PLAUSIBLE against publicly available VBA data, though the baseline date matters" — this is the kind of nuanced, actionable framing the machine cannot produce.

2. **No comparative framing.** The brief presents this week's top signals but does not compare them to last week, identify trends, or note what has dropped off the radar. The `Delta` dataclass (schema.py:166-179) exists but only contains "what changed," not "what changed about what we were tracking."

3. **Static stakeholder intelligence.** The system cannot tell the Commander "Senator X, who you met with last month, just introduced legislation related to your last discussion." Relationship context is absent.

4. **Padding obscures signal quality.** When the system lacks 3 real messages, it generates "Continue monitoring policy developments" (generator.py:162-165). This is a cognitive trap — it makes every brief look equally dense, preventing the Commander from detecting quiet periods that might themselves be signals.

---

## 4. Anchor Pack Quality Assessment

### Analysis of Sample Packs

**Cash v. Collins (24-1811)** — `~/.vigil/vnn-anchor-packs/2026-02-06-auto-cash-v-collins-opinion-24-1811.yaml`

- **Confidence label:** VERIFIED (correct — CAFC opinion is authoritative)
- **Facts:** Only 2 facts, both essentially the same thing (title + "OPINION - Precedential"). No extraction of what the opinion actually decided.
- **why_veterans_care:** Generic: "Oversight reports can reveal systemic issues..." This is wrong — this is a court opinion, not an oversight report. The generator used `OversightPackGenerator` because CAFC is in the oversight pipeline, but the "why it matters" text is oversight-templated, not legal-templated.
- **Script draft:** Repeats the same generic framing. A veteran watching this would learn nothing about what the case decided.

**Disability Assistance Hearing** — `2026-02-06-auto-disability-assistance-chairman-luttrell...`

- **Confidence label:** VERIFIED (correct)
- **Facts:** Correctly captures the hearing topic and chairman
- **why_veterans_care:** Same generic oversight template: "Oversight reports can reveal systemic issues..."
- **Caption truncated:** Text cuts off mid-word at the character limit

### Misinformation Entry Points

1. **Template reuse across source types.** `OversightPackGenerator` (anchor_pack_generator.py:208-253) uses identical `why_veterans_care`, `what_to_watch`, and `risk_flags` for GAO reports, OIG reports, CRS reports, CAFC opinions, and committee press releases. These have fundamentally different implications for veterans. A court precedent is not an oversight report.

2. **No content extraction.** The generator works from structured metadata (title, date, URL) but does not read the actual document content. For bills, it has `latest_action_text`; for oversight events, it has `summary`. But the generated packs rarely reflect the substance of the document.

3. **"Review required before production" is the only gate.** Line 4 of every pack: "# Review required before production." This is the correct control, but it means anchor pack quality depends entirely on the Commander (or a human reviewer) catching template-generated inaccuracies. If review is skipped, generic and potentially incorrect framing reaches veterans.

4. **No fact-checking against source.** The anchor pack generator does not verify its generated facts against the actual document. It trusts the pipeline metadata blindly.

---

## 5. C2 Channel Assessment

### Architecture

The C2 system (`~/.vigil/c2/`) implements a disciplined command-response pattern:

```
Commander (iMessage) → BlueBubbles → Flask webhook → Classifier → Executor → Claude CLI → Response
```

### Strengths

1. **Single-commander authorization.** `security.py:73-79` — Only the configured `commander_phone` can issue commands. No multi-user ambiguity.

2. **Classification taxonomy is sound.** `classifier.py` separates SHORTCUT (instant, no-LLM), ACK (no response needed), QUERY (read-only LLM call), and ORDER (multi-step with write access). This is appropriate graduated capability.

3. **Order decomposition with progress updates.** `executor.py:280-431` — Multi-step orders get decomposed, each step gets a progress message ("[Step 2/5] Querying VA signals database..."), and the Commander sees execution unfold in real-time. This is good situational awareness.

4. **Outbound scrubbing.** `security.py:142-163` — API keys, SSNs, bearer tokens are scrubbed before any text leaves the system. This prevents sensitive data leakage via iMessage.

5. **Crash recovery.** `executor.py:709-789` — On daemon restart, interrupted orders are identified, marked failed, and the Commander is notified. No silent failures.

### Weaknesses

1. **No situational awareness summary.** The Commander can text "status" or "sitrep" for point-in-time snapshots, but there is no proactive "morning briefing" push via C2. The outbound queue (`daemon.py:308-334`) exists but is reactive (processes queued messages), not proactively synthesizing context.

2. **Conversational context is shallow.** `executor.py:184-188` — Recent context includes last 6 messages with 200-char truncation. For complex multi-turn intelligence discussions, this is insufficient. The Commander might ask "What about that bill I asked about yesterday?" and the context window won't reach it.

3. **iMessage is a poor C2 medium for structured data.** The responder sends plain text chunked at 2000 characters (`responder.py:76-118`). Tables, risk matrices, and stakeholder maps lose all formatting. The QUERY response rules (executor.py:197-198) explicitly ban markdown headers and bullet points because they render badly on phone screens. This forces all intelligence into prose paragraphs, which increases cognitive load.

4. **No push notification priority levels.** Outbound messages are sent FIFO with uniform priority. A critical escalation and a routine status update compete equally for the Commander's attention on a phone screen.

---

## 6. Cognitive Load Analysis

### Dashboard (`src/dashboard/static/`)

The dashboard manages ~15 parallel data streams (index.html, app.js state object lines 19-83):

- Federal Register documents
- eCFR documents
- Bill tracking
- Hearing tracking
- Oversight events
- State signals
- Agenda drift events
- Battlefield gates/vehicles/alerts
- Trend data
- Source runs
- Health status

**Cognitive load assessment:** HIGH. The `app.js` state object tracks 44 distinct state variables, 16 loading states, and 8+ DOM element groups. The classification banner reads "UNCLASSIFIED // FOR OFFICIAL USE ONLY" — appropriate framing. But the dashboard presents all data streams at equal visual weight. There is no:

- **Priority-weighted layout.** All tabs get equal real estate. The Commander must decide where to look.
- **Anomaly highlighting.** No visual differentiation between "normal day, 50 signals processed" and "crisis day, 3 escalations detected."
- **Decision-ready view.** The CEO Brief is accessible via API but has no dedicated dashboard panel. The Commander must navigate to a separate endpoint.
- **Cognitive budget management.** Miller's Law (7 +/- 2 items) is violated by every panel. The bills table, hearings list, oversight events, and state signals all present unbounded lists.

### Briefings (`~/.vigil/briefings/`)

The human-written daily briefing (2026-02-06.md) demonstrates excellent cognitive design:

1. **BLUF (Bottom Line Up Front)** — lines 9-11: one paragraph summary with priority assessment
2. **Tables for structured data** — lines 23-26, 29-35: comment deadlines, claims data
3. **Standing Order annotations inline** — lines 57, 110, 112: SO#1 and cui bono notes are embedded where the data appears, not in a separate section
4. **Progressive disclosure** — Morning brief at top, evening pulse update appended below
5. **Explicit uncertainty markers** — "MEDIUM-HIGH," "PLAUSIBLE," "verify"
6. **Action items at end** — lines 157-160: numbered, specific, operational

This briefing is the gold standard output of the system. It is also entirely human-produced. The gap between this and the machine-generated CEO Brief is the core decision quality deficit.

---

## 7. Human-AI Teaming Effectiveness Assessment

### Current Division of Labor

| Function | Human (Commander/CDR Vigil) | Machine (VA Signals + Pipeline) |
|----------|---------------------------|--------------------------------|
| Signal Collection | - | Fully automated, 30+ sources |
| Classification | Manual override for nuance | Keyword regex + Haiku LLM |
| Deviation Detection | Manual pattern recognition | Sonnet LLM + heuristic |
| Escalation | Manual judgment | Keyword matching + ML scoring |
| Cross-signal Synthesis | Manual (briefings) | NOT IMPLEMENTED |
| Standing Orders | Manual enforcement | Partial (source authority scoring only) |
| Brief Generation | Manual (daily briefing) | Template-based (CEO Brief) |
| Anchor Packs | Manual review gate | Template generation |
| C2 Response | - | Claude CLI via executor |

### Assessment

The system is a **high-quality collection and classification pipeline** paired with a **weak synthesis and presentation layer**. The human analyst (CDR Vigil via heartbeat) does the cognitive heavy-lifting that transforms signals into intelligence. The machine provides the data; the human provides the meaning.

This is not a criticism — it is appropriate for the current maturity level. But it means the system scales with the Commander's cognitive bandwidth, not independently. If the Commander goes offline for 3 days, the pipeline will continue collecting and scoring signals, but no briefings will be produced and no anchor packs will receive substantive review.

### The Vigil Bridge Paradox

The system's most impressive output (the daily briefing) and its most important gate (anchor pack review) are both fully manual. The automation handles the high-volume, low-judgment work. The human handles the low-volume, high-judgment work. This is the correct allocation — but it means the system's decision quality ceiling IS the Commander's decision quality ceiling.

---

## 8. Top 5 Decision Quality Improvements (Ranked by Commander Impact)

### 1. Add Confidence Scoring to CEO Brief Pipeline (HIGHEST IMPACT)

**Current state:** Impact and urgency scores exist. Confidence does not.
**What to add:** A `confidence_score` (0-1) on each `AggregatedDelta` that tracks source agreement/disagreement and claim verifiability.
**Why it matters:** The Commander currently cannot distinguish between "5 authoritative sources confirm this" and "1 news wire reported this with no corroboration." This is the most dangerous gap for decision quality.
**Files:** `src/ceo_brief/aggregator.py` (add field to `AggregatedDelta`), `src/ceo_brief/schema.py` (add to `Delta`, `Message`), `src/ceo_brief/analyst.py` (surface in messages).

### 2. Implement Competing Hypothesis Section in CEO Brief

**Current state:** Brief presents top-ranked signals as if they tell one story.
**What to add:** After messages, add a "Competing Interpretations" section that presents at least one alternative framing. Use the same signals but reverse the conclusion.
**Why it matters:** This is Standing Orders #1 and #5 in code form. The Commander already does this manually in briefings (line 152: "The truth likely sits between..."). The machine should support, not replace, this habit.
**Files:** `src/ceo_brief/schema.py` (new `CompetingHypothesis` dataclass), `src/ceo_brief/analyst.py` (generate alternatives), `src/ceo_brief/generator.py` (include in brief).

### 3. Fix Anchor Pack Template Specificity

**Current state:** All oversight-category packs get identical `why_veterans_care` and `risk_flags` regardless of source type.
**What to add:** Differentiate templates by `primary_source_type`: GAO reports, OIG reports, CAFC opinions, CRS reports, and committee press all get type-specific framing.
**Why it matters:** Generic packs reaching veterans without review are a misinformation vector. A CAFC opinion described as an "oversight report" is factually wrong and erodes trust in the VNN product.
**Files:** `~/.vigil/integrations/anchor_pack_generator.py:208-253` — split `OversightPackGenerator` into `GaoPackGenerator`, `OigPackGenerator`, `CafcPackGenerator`, `CommitteePackGenerator`.

### 4. Add "What Dropped Off" Tracking to CEO Brief

**Current state:** Brief shows what's new. Nothing shows what was tracked last week but no longer appears.
**What to add:** Track previous brief's top issues. In the new brief, add a section: "Previously Tracked — No Longer Active" for items that were top-5 last week but absent this week.
**Why it matters:** Intelligence is about absence as much as presence. A bill that was "hearing_scheduled" last week and has no action this week might mean it was tabled — which is itself a signal. The Commander needs to see what disappeared.
**Files:** `src/ceo_brief/aggregator.py` (query previous brief), `src/ceo_brief/generator.py` (new section), `src/ceo_brief/schema.py` (new `DroppedIssue` dataclass).

### 5. Add LLM Synthesis Step to Analyst Pipeline

**Current state:** `analyst.py` is entirely heuristic — no LLM call.
**What to add:** After template-based message generation, pass the top 5 signals through a single Claude Haiku call that synthesizes: "Given these 5 signals, what is the one sentence a CEO needs to hear?"
**Why it matters:** The gap between the human briefing (nuanced, contextual, actionable) and the machine CEO Brief (templated, mechanical, generic) is the synthesis step. Even a small LLM enhancement would dramatically improve talking point quality while preserving the deterministic scoring pipeline underneath.
**Files:** `src/ceo_brief/analyst.py` (add `_synthesize_executive_summary()`), `src/ceo_brief/schema.py` (add `executive_synthesis` field to `CEOBrief`).

---

## 9. Philosophical Observations

### On the Nature of Intelligence in This System

The system embodies a fundamental tension: it is built to produce **intelligence** (in the military/policy sense) but its automated pipeline produces **information** (scored, classified, formatted data). The transformation from information to intelligence requires judgment — specifically, the judgment of what matters *given what we are trying to do*. The aggregator scores for impact and relevance, but it does not model the Commander's intent, current priorities, or operational context.

The daily briefing bridges this gap because it IS the Commander's judgment, encoded by a human analyst (CDR Vigil). The question for system advancement is not "how do we replace this judgment?" but "how do we augment it?" — providing the Commander with better raw material, better counterfactual framing, and better uncertainty quantification so that the human synthesis step is faster and more accurate.

### On Standing Orders as a Design Pattern

The 5 Standing Orders are a remarkable design artifact. They function as cognitive forcing functions — structured prompts that prevent the Commander from falling into known decision-making traps (confirmation bias, source confusion, false certainty, cui bono blindness, narrative lock-in). The system would benefit from treating these not as human-enforced guidelines but as machine-enforceable quality gates, applied at every stage of the pipeline.

---

*Assessment by Expert #4 (Cognitive Science & Philosophy)*
*Task #4 — Cognitive Architecture & Decision Quality*
