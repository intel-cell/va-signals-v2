CREATE TABLE IF NOT EXISTS source_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT NOT NULL,
  status TEXT NOT NULL,
  records_fetched INTEGER NOT NULL DEFAULT 0,
  errors_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS fr_seen (
  doc_id TEXT PRIMARY KEY,
  published_date TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  source_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ecfr_seen (
  doc_id TEXT PRIMARY KEY,
  last_modified TEXT,
  etag TEXT,
  first_seen_at TEXT NOT NULL,
  source_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fr_summaries (
  doc_id TEXT PRIMARY KEY,
  summary TEXT NOT NULL,
  bullet_points TEXT NOT NULL,
  veteran_impact TEXT NOT NULL,
  tags TEXT NOT NULL,
  summarized_at TEXT NOT NULL,
  FOREIGN KEY (doc_id) REFERENCES fr_seen(doc_id)
);

-- Agenda Drift Detection tables

CREATE TABLE IF NOT EXISTS ad_members (
  member_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  party TEXT,
  committee TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ad_utterances (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  utterance_id TEXT UNIQUE NOT NULL,
  member_id TEXT NOT NULL,
  hearing_id TEXT NOT NULL,
  chunk_ix INTEGER NOT NULL DEFAULT 0,
  content TEXT NOT NULL,
  spoken_at TEXT NOT NULL,
  ingested_at TEXT NOT NULL,
  FOREIGN KEY (member_id) REFERENCES ad_members(member_id)
);

CREATE TABLE IF NOT EXISTS ad_embeddings (
  utterance_id TEXT PRIMARY KEY,
  vec TEXT NOT NULL,
  model_id TEXT NOT NULL,
  embedded_at TEXT NOT NULL,
  FOREIGN KEY (utterance_id) REFERENCES ad_utterances(utterance_id)
);

CREATE TABLE IF NOT EXISTS ad_baselines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  member_id TEXT NOT NULL,
  built_at TEXT NOT NULL,
  vec_mean TEXT NOT NULL,
  mu REAL NOT NULL,
  sigma REAL NOT NULL,
  n INTEGER NOT NULL,
  FOREIGN KEY (member_id) REFERENCES ad_members(member_id)
);

CREATE TABLE IF NOT EXISTS ad_deviation_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  member_id TEXT NOT NULL,
  hearing_id TEXT NOT NULL,
  utterance_id TEXT NOT NULL,
  baseline_id INTEGER NOT NULL,
  cos_dist REAL NOT NULL,
  zscore REAL NOT NULL,
  detected_at TEXT NOT NULL,
  note TEXT,
  FOREIGN KEY (member_id) REFERENCES ad_members(member_id),
  FOREIGN KEY (utterance_id) REFERENCES ad_utterances(utterance_id),
  FOREIGN KEY (baseline_id) REFERENCES ad_baselines(id)
);

-- VA Bills tracking
CREATE TABLE IF NOT EXISTS bills (
  bill_id TEXT PRIMARY KEY,
  congress INTEGER NOT NULL,
  bill_type TEXT NOT NULL,
  bill_number INTEGER NOT NULL,
  title TEXT NOT NULL,
  sponsor_name TEXT,
  sponsor_bioguide_id TEXT,
  sponsor_party TEXT,
  sponsor_state TEXT,
  introduced_date TEXT,
  latest_action_date TEXT,
  latest_action_text TEXT,
  policy_area TEXT,
  committees_json TEXT,
  cosponsors_count INTEGER DEFAULT 0,
  first_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bill_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bill_id TEXT NOT NULL,
  action_date TEXT NOT NULL,
  action_text TEXT NOT NULL,
  action_type TEXT,
  first_seen_at TEXT NOT NULL,
  FOREIGN KEY (bill_id) REFERENCES bills(bill_id),
  UNIQUE(bill_id, action_date, action_text)
);

-- Committee hearings
CREATE TABLE IF NOT EXISTS hearings (
  event_id TEXT PRIMARY KEY,
  congress INTEGER NOT NULL,
  chamber TEXT NOT NULL,
  committee_code TEXT NOT NULL,
  committee_name TEXT,
  hearing_date TEXT NOT NULL,
  hearing_time TEXT,
  title TEXT,
  meeting_type TEXT,
  status TEXT NOT NULL,
  location TEXT,
  url TEXT,
  witnesses_json TEXT,
  first_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hearing_updates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  field_changed TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT,
  detected_at TEXT NOT NULL,
  FOREIGN KEY (event_id) REFERENCES hearings(event_id)
);

-- ============================================================================
-- OVERSIGHT MONITOR TABLES
-- ============================================================================

-- Canonical events (deduplicated, entity-centric)
CREATE TABLE IF NOT EXISTS om_events (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  theme TEXT,
  primary_source_type TEXT NOT NULL,
  primary_url TEXT NOT NULL,

  pub_timestamp TEXT,
  pub_precision TEXT NOT NULL,
  pub_source TEXT NOT NULL,
  event_timestamp TEXT,
  event_precision TEXT,
  event_source TEXT,

  title TEXT NOT NULL,
  summary TEXT,
  raw_content TEXT,

  is_escalation INTEGER DEFAULT 0,
  escalation_signals TEXT,
  is_deviation INTEGER DEFAULT 0,
  deviation_reason TEXT,
  canonical_refs TEXT,

  surfaced INTEGER DEFAULT 0,
  surfaced_at TEXT,
  surfaced_via TEXT,

  fetched_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_om_events_theme ON om_events(theme);
CREATE INDEX IF NOT EXISTS idx_om_events_pub_timestamp ON om_events(pub_timestamp);
CREATE INDEX IF NOT EXISTS idx_om_events_surfaced ON om_events(surfaced, surfaced_at);
CREATE INDEX IF NOT EXISTS idx_om_events_source_type ON om_events(primary_source_type);

-- Related coverage
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
  topic_distribution TEXT,
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
  rejection_reason TEXT NOT NULL,
  routine_explanation TEXT,
  fetched_at TEXT NOT NULL,
  rejected_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_om_rejected_date ON om_rejected(rejected_at);

-- Configurable escalation signals
CREATE TABLE IF NOT EXISTS om_escalation_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_pattern TEXT NOT NULL,
  signal_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  description TEXT,
  active INTEGER DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Weekly digest history
CREATE TABLE IF NOT EXISTS om_digests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  digest_type TEXT NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  event_ids TEXT NOT NULL,
  theme_groups TEXT NOT NULL,
  delivered_at TEXT,
  delivered_via TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

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
CREATE INDEX IF NOT EXISTS idx_state_signals_source_id ON state_signals(source_id);

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
CREATE INDEX IF NOT EXISTS idx_state_runs_state_status ON state_runs(state, status);

-- Source health tracking
CREATE TABLE IF NOT EXISTS state_source_health (
    source_id TEXT PRIMARY KEY,
    consecutive_failures INTEGER DEFAULT 0,
    last_success TEXT,
    last_failure TEXT,
    last_error TEXT,
    FOREIGN KEY (source_id) REFERENCES state_sources(source_id)
);

CREATE INDEX IF NOT EXISTS idx_state_source_health_source_id ON state_source_health(source_id);

-- ============================================================================
-- SIGNALS ROUTING TABLES
-- ============================================================================

-- Signals routing suppression state
CREATE TABLE IF NOT EXISTS signal_suppression (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key TEXT UNIQUE NOT NULL,
    trigger_id TEXT NOT NULL,
    authority_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    last_fired_at TEXT NOT NULL,
    cooldown_until TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signal_suppression_dedupe ON signal_suppression(dedupe_key);
CREATE INDEX IF NOT EXISTS idx_signal_suppression_cooldown ON signal_suppression(cooldown_until);

-- Signal audit log
CREATE TABLE IF NOT EXISTS signal_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    authority_id TEXT NOT NULL,
    indicator_id TEXT NOT NULL,
    trigger_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    fired_at TEXT NOT NULL,
    suppressed INTEGER NOT NULL DEFAULT 0,
    suppression_reason TEXT,
    explanation_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_signal_audit_trigger ON signal_audit_log(trigger_id, fired_at);
CREATE INDEX IF NOT EXISTS idx_signal_audit_event ON signal_audit_log(event_id);

-- ============================================================================
-- AUTHORITY LAYER TABLES
-- ============================================================================

-- Authority documents from executive branch and VA leadership
CREATE TABLE IF NOT EXISTS authority_docs (
    doc_id TEXT PRIMARY KEY,
    authority_source TEXT NOT NULL,  -- whitehouse, omb, va, omb_oira, knowva
    authority_type TEXT NOT NULL,    -- bill_signing, executive_order, memorandum, directive, etc.
    title TEXT NOT NULL,
    published_at TEXT,
    source_url TEXT NOT NULL,
    body_text TEXT,
    content_hash TEXT,
    version INTEGER DEFAULT 1,
    metadata_json TEXT,
    fetched_at TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    updated_at TEXT,
    routed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_authority_docs_source ON authority_docs(authority_source, published_at);
CREATE INDEX IF NOT EXISTS idx_authority_docs_hash ON authority_docs(content_hash);
CREATE INDEX IF NOT EXISTS idx_authority_docs_routed ON authority_docs(routed_at);

-- ============================================================================
-- EVIDENCE PACK TABLES (BRAVO COMMAND)
-- ============================================================================

-- Evidence packs: containers for claims and their supporting sources
CREATE TABLE IF NOT EXISTS evidence_packs (
    pack_id TEXT PRIMARY KEY,
    issue_id TEXT,                        -- Link to issue register (optional)
    title TEXT NOT NULL,
    summary TEXT,
    generated_at TEXT NOT NULL,
    generated_by TEXT NOT NULL,           -- Agent/user that created the pack
    status TEXT NOT NULL DEFAULT 'draft', -- draft, validated, published
    validation_passed INTEGER DEFAULT 0,
    validation_errors TEXT,               -- JSON array of validation failures
    output_path TEXT,                     -- Path to generated markdown file
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_packs_issue ON evidence_packs(issue_id);
CREATE INDEX IF NOT EXISTS idx_evidence_packs_status ON evidence_packs(status);

-- Evidence sources: authoritative citations
CREATE TABLE IF NOT EXISTS evidence_sources (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,            -- federal_register, bill, hearing, oig_report, gao_report, crs_report, va_guidance, authority_doc
    title TEXT NOT NULL,
    date_published TEXT,
    date_effective TEXT,                  -- For regulations: effective date
    date_accessed TEXT NOT NULL,          -- When we retrieved it
    url TEXT NOT NULL,                    -- Primary source link
    document_hash TEXT,                   -- SHA256 of content for change detection
    version INTEGER DEFAULT 1,

    -- Source-type-specific identifiers
    fr_citation TEXT,                     -- e.g., "89 FR 12345"
    fr_doc_number TEXT,                   -- e.g., "2024-01234"
    bill_number TEXT,                     -- e.g., "HR5", "S1234"
    bill_congress INTEGER,                -- e.g., 118
    report_number TEXT,                   -- e.g., "GAO-24-123", "22-00123-45"

    -- Metadata
    issuing_agency TEXT,
    document_type TEXT,                   -- rule, proposed_rule, notice, report, testimony
    metadata_json TEXT,

    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_sources_type ON evidence_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_evidence_sources_fr ON evidence_sources(fr_doc_number);
CREATE INDEX IF NOT EXISTS idx_evidence_sources_bill ON evidence_sources(bill_number, bill_congress);
CREATE INDEX IF NOT EXISTS idx_evidence_sources_report ON evidence_sources(report_number);

-- Evidence excerpts: specific quotes from sources
CREATE TABLE IF NOT EXISTS evidence_excerpts (
    excerpt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    section_reference TEXT,               -- e.g., "Section 3(a)(1)", "Page 15, Para 2"
    excerpt_text TEXT NOT NULL,           -- Exact quote
    page_or_line TEXT,                    -- Page number or line reference
    context_before TEXT,                  -- Surrounding text for verification
    context_after TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (source_id) REFERENCES evidence_sources(source_id)
);

CREATE INDEX IF NOT EXISTS idx_evidence_excerpts_source ON evidence_excerpts(source_id);

-- Evidence claims: statements with supporting sources
CREATE TABLE IF NOT EXISTS evidence_claims (
    claim_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL DEFAULT 'observed',  -- observed, inferred, modeled
    confidence TEXT NOT NULL DEFAULT 'high',      -- high, medium, low
    last_verified TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (pack_id) REFERENCES evidence_packs(pack_id)
);

CREATE INDEX IF NOT EXISTS idx_evidence_claims_pack ON evidence_claims(pack_id);
CREATE INDEX IF NOT EXISTS idx_evidence_claims_type ON evidence_claims(claim_type);

-- Claim-source links: which sources support which claims
CREATE TABLE IF NOT EXISTS evidence_claim_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    excerpt_id INTEGER,                   -- Optional: specific excerpt supporting claim
    relevance_note TEXT,                  -- Why this source supports the claim
    FOREIGN KEY (claim_id) REFERENCES evidence_claims(claim_id),
    FOREIGN KEY (source_id) REFERENCES evidence_sources(source_id),
    FOREIGN KEY (excerpt_id) REFERENCES evidence_excerpts(excerpt_id),
    UNIQUE(claim_id, source_id, excerpt_id)
);

CREATE INDEX IF NOT EXISTS idx_evidence_claim_sources_claim ON evidence_claim_sources(claim_id);
CREATE INDEX IF NOT EXISTS idx_evidence_claim_sources_source ON evidence_claim_sources(source_id);

-- ============================================================================
-- IMPACT TRANSLATION TABLES (CHARLIE COMMAND - LOE 3)
-- ============================================================================

-- Impact Memos - CEO-grade policy impact assessments
CREATE TABLE IF NOT EXISTS impact_memos (
    memo_id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    generated_date TEXT NOT NULL,

    -- Policy Hook
    policy_vehicle TEXT NOT NULL,          -- Bill number, rule docket, etc.
    policy_vehicle_type TEXT NOT NULL,     -- bill, rule, hearing, report
    policy_section_reference TEXT,
    policy_current_status TEXT NOT NULL,
    policy_source_url TEXT NOT NULL,
    policy_effective_date TEXT,

    -- What It Does
    what_it_does TEXT NOT NULL,

    -- Why It Matters - Operational
    operational_impact TEXT NOT NULL,
    affected_workflows TEXT NOT NULL,       -- JSON array
    affected_veteran_count TEXT,

    -- Why It Matters - Compliance
    compliance_exposure TEXT NOT NULL,      -- critical|high|medium|low|negligible
    enforcement_mechanism TEXT,
    compliance_deadline TEXT,

    -- Why It Matters - Cost
    cost_impact TEXT,
    cost_type TEXT,

    -- Why It Matters - Reputational
    reputational_risk TEXT NOT NULL,        -- critical|high|medium|low|negligible
    narrative_vulnerability TEXT,

    -- Posture & Action
    our_posture TEXT NOT NULL,              -- support|oppose|monitor|neutral_engaged
    recommended_action TEXT NOT NULL,
    decision_trigger TEXT NOT NULL,

    -- Metadata
    confidence_level TEXT NOT NULL,         -- high|medium|low
    sources_json TEXT NOT NULL DEFAULT '[]', -- JSON array of evidence pack links
    translated_by TEXT NOT NULL DEFAULT 'charlie_command',
    translation_method TEXT NOT NULL DEFAULT 'rule_based',

    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_impact_memos_issue ON impact_memos(issue_id);
CREATE INDEX IF NOT EXISTS idx_impact_memos_posture ON impact_memos(our_posture);
CREATE INDEX IF NOT EXISTS idx_impact_memos_compliance ON impact_memos(compliance_exposure);
CREATE INDEX IF NOT EXISTS idx_impact_memos_generated ON impact_memos(generated_date);

-- Heat Maps - Risk matrices for issue prioritization
CREATE TABLE IF NOT EXISTS heat_maps (
    heat_map_id TEXT PRIMARY KEY,
    generated_date TEXT NOT NULL,
    issues_json TEXT NOT NULL,              -- JSON array of heat map issues
    summary_json TEXT NOT NULL,             -- JSON object with counts
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_heat_maps_generated ON heat_maps(generated_date);

-- Heat Map Issues - Individual issue scores (denormalized for queries)
CREATE TABLE IF NOT EXISTS heat_map_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    heat_map_id TEXT NOT NULL,
    issue_id TEXT NOT NULL,
    title TEXT NOT NULL,
    likelihood INTEGER NOT NULL,            -- 1-5
    impact INTEGER NOT NULL,                -- 1-5
    urgency_days INTEGER NOT NULL,
    score REAL NOT NULL,
    quadrant TEXT NOT NULL,                 -- high_priority|watch|monitor|low
    memo_id TEXT,                           -- Link to impact_memos
    FOREIGN KEY (heat_map_id) REFERENCES heat_maps(heat_map_id),
    FOREIGN KEY (memo_id) REFERENCES impact_memos(memo_id)
);

CREATE INDEX IF NOT EXISTS idx_heat_map_issues_map ON heat_map_issues(heat_map_id);
CREATE INDEX IF NOT EXISTS idx_heat_map_issues_quadrant ON heat_map_issues(quadrant);
CREATE INDEX IF NOT EXISTS idx_heat_map_issues_score ON heat_map_issues(score DESC);

-- Objection Library - Staff pushback responses
CREATE TABLE IF NOT EXISTS objections (
    objection_id TEXT PRIMARY KEY,
    issue_area TEXT NOT NULL,               -- benefits|accreditation|appropriations|oversight|etc
    source_type TEXT NOT NULL,              -- staff|vso|industry|media|congressional|va_internal
    objection_text TEXT NOT NULL,           -- What they'll say
    response_text TEXT NOT NULL,            -- 1-2 sentence reply
    supporting_evidence_json TEXT NOT NULL DEFAULT '[]', -- JSON array of evidence links
    last_used_date TEXT,
    effectiveness_rating INTEGER,           -- 1-5 scale
    tags_json TEXT NOT NULL DEFAULT '[]',   -- JSON array of tags
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_objections_area ON objections(issue_area);
CREATE INDEX IF NOT EXISTS idx_objections_source ON objections(source_type);
CREATE INDEX IF NOT EXISTS idx_objections_rating ON objections(effectiveness_rating DESC);

-- ============================================================================
-- AUDIT & COMPLIANCE TABLES
-- ============================================================================

-- Audit log for API request tracking and compliance
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id TEXT UNIQUE NOT NULL,            -- AUDIT_YYYYMMDD_xxxxxxxxxxxx
    timestamp TEXT NOT NULL,
    user_id TEXT,
    user_email TEXT,
    action TEXT NOT NULL,                   -- auth:login, api:read, user:create, etc.
    resource TEXT,                          -- runs, bills, hearings, etc.
    resource_id TEXT,
    request_method TEXT,                    -- GET, POST, PUT, PATCH, DELETE
    request_path TEXT,
    request_body TEXT,                      -- Sanitized body (sensitive fields redacted)
    response_status INTEGER,
    ip_address TEXT,
    user_agent TEXT,
    duration_ms INTEGER,
    success INTEGER NOT NULL DEFAULT 1      -- 1=success, 0=failure
);

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_email, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_success ON audit_log(success, timestamp);
