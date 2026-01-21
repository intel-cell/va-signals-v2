# Signals Routing Layer Design

**Status:** Finalized
**Owner:** VetClaims.ai Signals Cell
**Created:** 2026-01-21
**Schema Version:** 1.0

---

## Executive Summary

This document defines the **Signals Routing Layer**—a downstream semantic routing and decision-trigger layer that operates on authority-validated events. It implements the Signal → Indicator → Trigger → Action control flow for the VA disability policy monitoring system.

**Core invariant:** This layer NEVER fetches. It receives events from upstream pipelines and classifies/routes them.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Authority-Validated Event Store              │
│         (om_events, fr_seen, bills, hearings, etc.)             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Event Adapter Layer                        │
│            (transforms source tables → normalized envelope)     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Signals Router                             │
│  ┌─────────────────┐    ┌──────────────────┐                    │
│  │  YAML Schema    │───▶│  Evaluation      │                    │
│  │  (categories,   │    │  Engine          │                    │
│  │   indicators,   │    │  (composes       │                    │
│  │   triggers)     │    │   evaluators)    │                    │
│  └─────────────────┘    └──────────────────┘                    │
│           │                      │                              │
│           ▼                      ▼                              │
│  ┌─────────────────┐    ┌──────────────────┐                    │
│  │  Evaluator      │    │  Explanation     │                    │
│  │  Registry       │    │  Payload Builder │                    │
│  │  (whitelist)    │    │  (deterministic) │                    │
│  └─────────────────┘    └──────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
        Trigger Evaluation              Routing Rules
        (did it fire?)             (where, urgency, cooldown)
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Output Channels                            │
│     Slack (#signals-oversight)  │  Exec Brief  │  Audit Log    │
└─────────────────────────────────────────────────────────────────┘
```

### Key Invariants

1. **Router never fetches** - It receives events from upstream pipelines
2. **YAML defines what** to evaluate; **Python defines how**
3. **Every trigger produces** a structured explanation payload
4. **Evaluator registry is a closed whitelist** - No arbitrary code execution
5. **Evaluation is pure boolean composition** - No channel/urgency/cooldown concerns
6. **Routing is pure delivery** - No content matching concerns

---

## Non-Goals and Explicit Constraints

| Constraint | Rationale |
|------------|-----------|
| **Never fetches** | Routing layer is judgment, not acquisition. Fetch separation enables authority-first reasoning and audit clarity. |
| **Not predictive** | System detects and routes signals; it does not forecast outcomes. |
| **Not TEVV** | Does not claim TEVV authority. Creates bridge to TEVV-style reasoning without overreach. |
| **No narrative generation** | Explanation payloads are structured fields, not prose. Determinism over interpretation. |
| **No implicit policy** | All trigger logic is explicit in YAML. No hidden heuristics in engine. |

---

## Normalized Event Envelope

The router consumes events through a single canonical envelope. Adapters transform source-specific records into this shape.

```yaml
envelope:
  # ── Identity ──────────────────────────────────────────────────
  event_id: "om-gao-abc123def456"           # Internal composite/hashed ID
  authority_id: "GAO-26-106123"             # Native ID from authority system

  # ── Authority (tight enum for PoC) ────────────────────────────
  authority_source: "congress_gov"          # govinfo | congress_gov | house_veterans | senate_veterans
  authority_type: "hearing_notice"          # hearing_notice | bill_text | rule | report | press_release

  # ── Classification Hints ──────────────────────────────────────
  committee: "HVAC"                         # HVAC | SVAC | null
  subcommittee: "Disability Assistance"     # Optional
  topics: ["disability_benefits", "exam_quality"]  # Controlled vocabulary

  # ── Content ───────────────────────────────────────────────────
  title: "Hearing: VA Disability Exam Quality"
  body_text: "..."

  # ── Change Detection ──────────────────────────────────────────
  content_hash: "sha256:a1b2c3..."          # Hash of normalized title + body_text
  version: 1                                 # Incremented when authority_id content changes

  # ── Temporal ──────────────────────────────────────────────────
  published_at: "2026-01-21T14:00:00Z"
  published_at_source: "authority"          # authority | derived
  event_start_at: "2026-02-15T10:00:00Z"    # Optional, for scheduled events

  # ── Provenance ────────────────────────────────────────────────
  source_url: "https://congress.gov/..."
  fetched_at: "2026-01-21T15:30:00Z"

  # ── Structured Metadata ───────────────────────────────────────
  metadata:
    status: "scheduled"                     # For hearings: scheduled|cancelled|rescheduled|postponed
    mentioned_entities: ["GAO", "OIG"]
```

### Adapter Contract

Each source pipeline (om_events, hearings, bills, fr_seen) has an adapter that emits this envelope. Router is decoupled from table schemas.

**What the envelope does NOT include:** Interpretation, severity, or routing decisions. Those are router outputs.

---

## Evaluator Registry

### Whitelist (PoC)

Only these evaluators may be referenced in YAML. Engine rejects any evaluator not in whitelist.

| Evaluator | Description | Args |
|-----------|-------------|------|
| `contains_any` | Returns true if field contains any of the specified terms (case-insensitive) | `field`, `terms[]` |
| `field_in` | Returns true if scalar field value is in the allowed list | `field`, `values[]` |
| `field_intersects` | Returns true if array field contains ANY of the specified values | `field`, `values[]` |
| `equals` | Returns true if field equals the specified value | `field`, `value` |
| `gt` | Returns true if field > value (numeric comparison) | `field`, `value` |
| `field_exists` | Returns true if field is present and not null | `field` |
| `nested_field_in` | Access nested field via dot notation and check if value is in list | `field`, `values[]` |

### Evaluator Output Contract

Each evaluator returns:

```python
{
    "passed": bool,
    "evidence": {
        # Evaluator-specific evidence fields
        "matched_terms": [...],      # For contains_any
        "actual_value": ...,         # For field_in, equals, gt
        "intersection": [...],       # For field_intersects
    }
}
```

### Normalization Rules

For `contains_any` evaluator:

| Rule | Value |
|------|-------|
| Case sensitivity | `false` |
| Unicode normalization | `NFKC` |
| Whitespace | `collapse_to_single_space` |
| Punctuation | `preserve` ("O.I.G." and "OIG" are different) |
| Match type | `substring` (not token-boundary; rely on anti-spam) |

**Note:** Substring matching may produce false positives; anti-spam discriminator mitigates.

---

## Expression Grammar

Every condition is an expression tree of these node types:

### Node Types

| Type | Shape | Description |
|------|-------|-------------|
| Evaluator node | `{ evaluator: <name>, args: {...} }` | Leaf node that calls a registry evaluator |
| all_of node | `{ all_of: [...], label?: "..." }` | AND - all child expressions must pass |
| any_of node | `{ any_of: [...], label?: "..." }` | OR - at least one child expression must pass |
| none_of node | `{ none_of: [...], label?: "..." }` | NOT ANY - all child expressions must fail |

### Validation Rules

1. Every list element must be a valid expression node
2. Evaluator name must exist in evaluator_registry
3. Args must match evaluator's args schema
4. Nesting depth limit: 5 levels
5. `label` is optional; used for evidence aggregation (e.g., `"anti_spam_discriminator"`)

---

## Field Access Policy

Evaluators may only access these envelope fields:

### Allowed Top-Level Fields

- `event_id`, `authority_id`
- `authority_source`, `authority_type`
- `committee`, `subcommittee`
- `topics`
- `title`, `body_text`
- `content_hash`, `version`
- `published_at`, `published_at_source`, `event_start_at`
- `source_url`, `fetched_at`

### Allowed Nested Prefix

- `metadata.*` only

---

## Oversight/Accountability PoC

### Summary

| Metric | Value |
|--------|-------|
| Indicators | 3 |
| Triggers | 5 |
| Severity levels used | medium, high |
| Output channels | slack, exec_brief, audit_log, oversight_pressure_register |

### Indicators and Triggers

```yaml
# ═══════════════════════════════════════════════════════════════════
# OVERSIGHT/ACCOUNTABILITY SIGNALS - PoC v1.0
# ═══════════════════════════════════════════════════════════════════

schema_version: "1.0"
category_id: "oversight_accountability"
description: "Oversight activity signaling increased scrutiny, audits, or enforcement"
priority: "high"
owner: "VetClaims.ai Signals Cell"
created_at: "2026-01-21"
last_updated: "2026-01-21"

# ─────────────────────────────────────────────────────────────────
# FIELD ACCESS POLICY
# ─────────────────────────────────────────────────────────────────

field_access:
  description: "Evaluators may only access these envelope fields"
  allowed_top_level:
    - event_id
    - authority_id
    - authority_source
    - authority_type
    - committee
    - subcommittee
    - topics
    - title
    - body_text
    - content_hash
    - version
    - published_at
    - published_at_source
    - event_start_at
    - source_url
    - fetched_at
  allowed_nested_prefix: "metadata."

# ─────────────────────────────────────────────────────────────────
# EVALUATOR WHITELIST (PoC)
# ─────────────────────────────────────────────────────────────────

evaluator_whitelist:
  - contains_any
  - field_in
  - field_intersects
  - equals
  - gt
  - field_exists
  - nested_field_in

# ─────────────────────────────────────────────────────────────────
# NORMALIZATION RULES
# ─────────────────────────────────────────────────────────────────

normalization:
  text_matching:
    description: "Rules for contains_any evaluator"
    case_sensitivity: false
    unicode_normalization: "NFKC"
    whitespace: "collapse_to_single_space"
    punctuation: "preserve"
    match_type: "substring"
    note: "Substring matching may produce false positives; anti-spam discriminator mitigates"

# ─────────────────────────────────────────────────────────────────
# INDICATORS & TRIGGERS
# ─────────────────────────────────────────────────────────────────

indicators:

  # ══════════════════════════════════════════════════════════════
  # INDICATOR 1: GAO/OIG Reference Detection
  # ══════════════════════════════════════════════════════════════

  - indicator_id: "gao_oig_reference"
    description: "Congressional events referencing GAO or OIG review of VA processes"

    indicator_condition:
      evaluator: "field_in"
      args:
        field: "authority_source"
        values: ["congress_gov", "house_veterans", "senate_veterans"]

    triggers:

      - trigger_id: "formal_audit_signal"
        description: "Direct reference to GAO, OIG, audit, or investigation"

        condition:
          all_of:
            - evaluator: "contains_any"
              args:
                field: "body_text"
                terms:
                  - "GAO"
                  - "Government Accountability Office"
                  - "OIG"
                  - "Office of Inspector General"
                  - "audit"
                  - "investigation"
            - any_of:
                - evaluator: "field_in"
                  args:
                    field: "committee"
                    values: ["HVAC", "SVAC"]
                - evaluator: "field_intersects"
                  args:
                    field: "topics"
                    values: ["disability_benefits", "rating", "exam_quality", "claims_backlog"]
                - evaluator: "field_in"
                  args:
                    field: "authority_type"
                    values: ["hearing_notice", "bill_text", "report"]
              label: "anti_spam_discriminator"

      - trigger_id: "contractor_exam_quality_signal"
        description: "References to contractor exam quality, MDEO, or C&P exams"

        condition:
          all_of:
            - evaluator: "contains_any"
              args:
                field: "body_text"
                terms:
                  - "contractor exam"
                  - "MDEO"
                  - "medical disability examination"
                  - "exam quality"
                  - "C&P exam"
                  - "compensation and pension exam"
            - any_of:
                - evaluator: "field_in"
                  args:
                    field: "committee"
                    values: ["HVAC", "SVAC"]
                - evaluator: "field_intersects"
                  args:
                    field: "topics"
                    values: ["exam_quality", "disability_benefits", "rating"]
                - evaluator: "field_in"
                  args:
                    field: "authority_type"
                    values: ["hearing_notice", "bill_text", "report"]
              label: "anti_spam_discriminator"

  # ══════════════════════════════════════════════════════════════
  # INDICATOR 2: Hearing Status Changes
  # ══════════════════════════════════════════════════════════════

  - indicator_id: "hearing_status"
    description: "Hearings scheduled, cancelled, or rescheduled on VA disability topics"

    indicator_condition:
      evaluator: "field_in"
      args:
        field: "authority_source"
        values: ["congress_gov", "house_veterans", "senate_veterans"]

    triggers:

      - trigger_id: "new_hearing_scheduled_va_disability"
        description: "New hearing scheduled on VA disability topics"

        condition:
          all_of:
            - evaluator: "field_in"
              args:
                field: "authority_type"
                values: ["hearing_notice"]
            - evaluator: "field_in"
              args:
                field: "committee"
                values: ["HVAC", "SVAC"]
            - evaluator: "field_intersects"
              args:
                field: "topics"
                values:
                  - "disability_benefits"
                  - "rating"
                  - "exam_quality"
                  - "claims_backlog"
                  - "vasrd"
                  - "appeals"
            - evaluator: "equals"
              args:
                field: "version"
                value: 1

      - trigger_id: "hearing_rescheduled_or_cancelled"
        description: "Existing hearing rescheduled or cancelled"

        condition:
          all_of:
            - evaluator: "field_in"
              args:
                field: "authority_type"
                values: ["hearing_notice"]
            - evaluator: "field_in"
              args:
                field: "committee"
                values: ["HVAC", "SVAC"]
            - any_of:
                - evaluator: "nested_field_in"
                  args:
                    field: "metadata.status"
                    values: ["cancelled", "rescheduled", "postponed"]
                - evaluator: "gt"
                  args:
                    field: "version"
                    value: 1
                - evaluator: "contains_any"
                  args:
                    field: "title"
                    terms: ["cancelled", "canceled", "rescheduled", "postponed"]
              label: "status_change_detector"

  # ══════════════════════════════════════════════════════════════
  # INDICATOR 3: Legislative Reporting Mandates
  # ══════════════════════════════════════════════════════════════

  - indicator_id: "legislative_mandate"
    description: "Bill text imposing reporting deadlines or mandated reviews"

    indicator_condition:
      evaluator: "field_in"
      args:
        field: "authority_source"
        values: ["congress_gov"]

    triggers:

      - trigger_id: "mandated_report_or_deadline"
        description: "Legislative language requiring reports or imposing deadlines"

        condition:
          all_of:
            - evaluator: "field_in"
              args:
                field: "authority_type"
                values: ["bill_text"]
            - evaluator: "contains_any"
              args:
                field: "body_text"
                terms:
                  - "shall report"
                  - "not later than"
                  - "within 90 days"
                  - "within 180 days"
                  - "GAO review"
                  - "submit to Congress"
            - any_of:
                - evaluator: "field_intersects"
                  args:
                    field: "topics"
                    values: ["disability_benefits", "rating", "vasrd", "exam_quality"]
                - evaluator: "contains_any"
                  args:
                    field: "body_text"
                    terms: ["disability", "rating schedule", "VASRD", "veterans benefits"]
              label: "anti_spam_discriminator"

# ─────────────────────────────────────────────────────────────────
# ROUTING RULES
# ─────────────────────────────────────────────────────────────────

routing:

  - trigger_id: "formal_audit_signal"
    severity: "high"
    human_review_required: true

    actions:
      - "post_slack_alert"
      - "create_exec_brief_card"
      - "write_audit_log"
      - "add_to_oversight_pressure_register"

    channels:
      - channel: "slack"
        target: "#signals-oversight"
        urgency: "immediate"
      - channel: "exec_brief"
        urgency: "next_cycle"
      - channel: "audit_log"
        urgency: "immediate"

    suppression:
      dedupe_key: ["trigger_id", "authority_id"]
      cooldown_minutes: 60
      version_aware: true

  - trigger_id: "contractor_exam_quality_signal"
    severity: "high"
    human_review_required: true

    actions:
      - "post_slack_alert"
      - "create_exec_brief_card"
      - "write_audit_log"
      - "flag_rating_integrity_concern"

    channels:
      - channel: "slack"
        target: "#signals-oversight"
        urgency: "immediate"
      - channel: "exec_brief"
        urgency: "next_cycle"
      - channel: "audit_log"
        urgency: "immediate"

    suppression:
      dedupe_key: ["trigger_id", "authority_id"]
      cooldown_minutes: 120
      version_aware: true

  - trigger_id: "new_hearing_scheduled_va_disability"
    severity: "medium"
    human_review_required: false

    actions:
      - "post_slack_alert"
      - "update_hearing_tracker"
      - "write_audit_log"

    channels:
      - channel: "slack"
        target: "#signals-oversight"
        urgency: "immediate"
      - channel: "exec_brief"
        urgency: "next_cycle"
      - channel: "audit_log"
        urgency: "immediate"

    suppression:
      dedupe_key: ["trigger_id", "authority_id"]
      cooldown_minutes: 1440
      version_aware: true

  - trigger_id: "hearing_rescheduled_or_cancelled"
    severity: "high"
    human_review_required: true

    actions:
      - "post_slack_alert"
      - "create_exec_brief_card"
      - "update_hearing_tracker"
      - "write_audit_log"

    channels:
      - channel: "slack"
        target: "#signals-oversight"
        urgency: "immediate"
      - channel: "exec_brief"
        urgency: "immediate"
      - channel: "audit_log"
        urgency: "immediate"

    suppression:
      dedupe_key: ["trigger_id", "authority_id"]
      cooldown_minutes: 30
      version_aware: true

  - trigger_id: "mandated_report_or_deadline"
    severity: "high"
    human_review_required: true

    actions:
      - "post_slack_alert"
      - "create_exec_brief_card"
      - "add_to_oversight_pressure_register"
      - "notify_product_policy_leads"
      - "write_audit_log"

    channels:
      - channel: "slack"
        target: "#signals-oversight"
        urgency: "immediate"
      - channel: "exec_brief"
        urgency: "next_cycle"
      - channel: "oversight_pressure_register"
        urgency: "next_cycle"
      - channel: "audit_log"
        urgency: "immediate"

    suppression:
      dedupe_key: ["trigger_id", "authority_id"]
      cooldown_minutes: 1440
      version_aware: true
```

---

## Explanation Payload Contract

Every trigger evaluation produces this deterministic output:

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `event_id` | string | envelope | Internal event ID |
| `authority_id` | string | envelope | Native ID from authority system |
| `authority_source` | string | envelope | Source authority |
| `indicator_id` | string | matched_indicator | Which indicator matched |
| `trigger_id` | string | matched_trigger | Which trigger fired |
| `matched_terms` | array[string] | engine | Terms that matched in contains_any |
| `matched_discriminators` | array[string] | engine | Evaluators from labeled discriminator node that passed |
| `passed_evaluators` | array[string] | engine | Format: `<trigger_id>:<path>:<evaluator_name>` |
| `failed_evaluators` | array[string] | engine | For debugging near-misses |
| `evidence_map` | object | engine | Keyed by eval_id, full evidence from each invocation |
| `severity` | string | routing_rule | low \| medium \| high \| critical |
| `actions` | array[string] | routing_rule | Actions to execute |
| `human_review_required` | boolean | routing_rule | Whether human review is needed |
| `fired_at` | iso8601 | engine | When trigger fired |
| `envelope_published_at` | iso8601 | envelope | Original publication time |
| `suppressed` | boolean | engine | Whether alert was suppressed |
| `suppression_reason` | string | engine | cooldown \| dedupe \| null |

---

## Implementation Guidance

### Phase 1: Engine Core
1. Implement evaluator registry with the 7 whitelisted evaluators
2. Build expression tree parser/validator
3. Implement evidence aggregation
4. Build suppression/cooldown state manager

### Phase 2: Adapters
1. Build normalized envelope adapters for: om_events, hearings, bills
2. Implement content_hash and version tracking
3. Ensure committee/topics fields are populated consistently

### Phase 3: Output Channels
1. Implement Slack alert formatter
2. Implement exec brief card generator
3. Implement audit log writer

### Phase 4: Integration
1. Wire router to receive events from upstream pipelines
2. Implement routing rule executor
3. End-to-end testing with real events

---

## Verification Checklist

- [ ] Engine rejects evaluators not in whitelist
- [ ] Engine rejects field access outside policy
- [ ] All triggers produce complete explanation payloads
- [ ] Suppression prevents duplicate alerts within cooldown
- [ ] Version-aware suppression re-alerts on content changes
- [ ] Labeled discriminator nodes populate matched_discriminators correctly
- [ ] Audit log captures all fired triggers (including suppressed)

---

## Future Categories (Not in PoC)

| Category | Phase | Notes |
|----------|-------|-------|
| VASRD Modernization | 2 | High salience, but semantically slippery |
| Disability Adjudication Rules | 2 | Federal Register parsing complexity |
| Benefit Access Restriction | 3 | Requires rule scope comparison |
| Judicial Interpretation | 3 | Requires CAFC/court integration |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-21 | Initial design finalized |
