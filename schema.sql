-- SQLite Schema for VA Signals (Unified)
-- Includes: Core, Oversight, Signals, Battlefield, Auth, CEO Brief

-- ============================================================================
-- CORE PIPELINE TABLES
-- ============================================================================

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
  source_url TEXT NOT NULL,
  comments_close_date TEXT,
  effective_date TEXT,
  document_type TEXT,
  title TEXT
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

-- ============================================================================
-- AGENDA DRIFT DETECTION
-- ============================================================================

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

-- ============================================================================
-- LEGISLATIVE TRACKING (BILLS & HEARINGS)
-- ============================================================================

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
-- OVERSIGHT MONITOR
-- ============================================================================

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

CREATE TABLE IF NOT EXISTS om_escalation_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_pattern TEXT NOT NULL,
  signal_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  description TEXT,
  active INTEGER DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

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
-- STATE INTELLIGENCE
-- ============================================================================

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

CREATE TABLE IF NOT EXISTS state_notifications (
    signal_id TEXT PRIMARY KEY,
    notified_at TEXT NOT NULL,
    channel TEXT NOT NULL,
    FOREIGN KEY (signal_id) REFERENCES state_signals(signal_id)
);

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
-- SIGNALS ROUTING
-- ============================================================================

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
-- AUTHORITY LAYER
-- ============================================================================

CREATE TABLE IF NOT EXISTS authority_docs (
    doc_id TEXT PRIMARY KEY,
    authority_source TEXT NOT NULL,
    authority_type TEXT NOT NULL,
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
-- EVIDENCE PACKS (BRAVO COMMAND)
-- ============================================================================

CREATE TABLE IF NOT EXISTS evidence_packs (
    pack_id TEXT PRIMARY KEY,
    issue_id TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    generated_at TEXT NOT NULL,
    generated_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    validation_passed INTEGER DEFAULT 0,
    validation_errors TEXT,
    output_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_packs_issue ON evidence_packs(issue_id);
CREATE INDEX IF NOT EXISTS idx_evidence_packs_status ON evidence_packs(status);

CREATE TABLE IF NOT EXISTS evidence_sources (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    title TEXT NOT NULL,
    date_published TEXT,
    date_effective TEXT,
    date_accessed TEXT NOT NULL,
    url TEXT NOT NULL,
    document_hash TEXT,
    version INTEGER DEFAULT 1,
    fr_citation TEXT,
    fr_doc_number TEXT,
    bill_number TEXT,
    bill_congress INTEGER,
    report_number TEXT,
    issuing_agency TEXT,
    document_type TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_sources_type ON evidence_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_evidence_sources_fr ON evidence_sources(fr_doc_number);
CREATE INDEX IF NOT EXISTS idx_evidence_sources_bill ON evidence_sources(bill_number, bill_congress);
CREATE INDEX IF NOT EXISTS idx_evidence_sources_report ON evidence_sources(report_number);

CREATE TABLE IF NOT EXISTS evidence_excerpts (
    excerpt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    section_reference TEXT,
    excerpt_text TEXT NOT NULL,
    page_or_line TEXT,
    context_before TEXT,
    context_after TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (source_id) REFERENCES evidence_sources(source_id)
);

CREATE INDEX IF NOT EXISTS idx_evidence_excerpts_source ON evidence_excerpts(source_id);

CREATE TABLE IF NOT EXISTS evidence_claims (
    claim_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL DEFAULT 'observed',
    confidence TEXT NOT NULL DEFAULT 'high',
    last_verified TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (pack_id) REFERENCES evidence_packs(pack_id)
);

CREATE INDEX IF NOT EXISTS idx_evidence_claims_pack ON evidence_claims(pack_id);
CREATE INDEX IF NOT EXISTS idx_evidence_claims_type ON evidence_claims(claim_type);

CREATE TABLE IF NOT EXISTS evidence_claim_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    excerpt_id INTEGER,
    relevance_note TEXT,
    FOREIGN KEY (claim_id) REFERENCES evidence_claims(claim_id),
    FOREIGN KEY (source_id) REFERENCES evidence_sources(source_id),
    FOREIGN KEY (excerpt_id) REFERENCES evidence_excerpts(excerpt_id),
    UNIQUE(claim_id, source_id, excerpt_id)
);

CREATE INDEX IF NOT EXISTS idx_evidence_claim_sources_claim ON evidence_claim_sources(claim_id);
CREATE INDEX IF NOT EXISTS idx_evidence_claim_sources_source ON evidence_claim_sources(source_id);

-- ============================================================================
-- IMPACT TRANSLATION (CHARLIE COMMAND)
-- ============================================================================

CREATE TABLE IF NOT EXISTS impact_memos (
    memo_id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    generated_date TEXT NOT NULL,
    policy_vehicle TEXT NOT NULL,
    policy_vehicle_type TEXT NOT NULL,
    policy_section_reference TEXT,
    policy_current_status TEXT NOT NULL,
    policy_source_url TEXT NOT NULL,
    policy_effective_date TEXT,
    what_it_does TEXT NOT NULL,
    operational_impact TEXT NOT NULL,
    affected_workflows TEXT NOT NULL,
    affected_veteran_count TEXT,
    compliance_exposure TEXT NOT NULL,
    enforcement_mechanism TEXT,
    compliance_deadline TEXT,
    cost_impact TEXT,
    cost_type TEXT,
    reputational_risk TEXT NOT NULL,
    narrative_vulnerability TEXT,
    our_posture TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    decision_trigger TEXT NOT NULL,
    confidence_level TEXT NOT NULL,
    sources_json TEXT NOT NULL DEFAULT '[]',
    translated_by TEXT NOT NULL DEFAULT 'charlie_command',
    translation_method TEXT NOT NULL DEFAULT 'rule_based',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_impact_memos_issue ON impact_memos(issue_id);
CREATE INDEX IF NOT EXISTS idx_impact_memos_posture ON impact_memos(our_posture);
CREATE INDEX IF NOT EXISTS idx_impact_memos_compliance ON impact_memos(compliance_exposure);
CREATE INDEX IF NOT EXISTS idx_impact_memos_generated ON impact_memos(generated_date);

CREATE TABLE IF NOT EXISTS heat_maps (
    heat_map_id TEXT PRIMARY KEY,
    generated_date TEXT NOT NULL,
    issues_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_heat_maps_generated ON heat_maps(generated_date);

CREATE TABLE IF NOT EXISTS heat_map_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    heat_map_id TEXT NOT NULL,
    issue_id TEXT NOT NULL,
    title TEXT NOT NULL,
    likelihood INTEGER NOT NULL,
    impact INTEGER NOT NULL,
    urgency_days INTEGER NOT NULL,
    score REAL NOT NULL,
    quadrant TEXT NOT NULL,
    memo_id TEXT,
    FOREIGN KEY (heat_map_id) REFERENCES heat_maps(heat_map_id),
    FOREIGN KEY (memo_id) REFERENCES impact_memos(memo_id)
);

CREATE INDEX IF NOT EXISTS idx_heat_map_issues_map ON heat_map_issues(heat_map_id);
CREATE INDEX IF NOT EXISTS idx_heat_map_issues_quadrant ON heat_map_issues(quadrant);
CREATE INDEX IF NOT EXISTS idx_heat_map_issues_score ON heat_map_issues(score DESC);

CREATE TABLE IF NOT EXISTS objections (
    objection_id TEXT PRIMARY KEY,
    issue_area TEXT NOT NULL,
    source_type TEXT NOT NULL,
    objection_text TEXT NOT NULL,
    response_text TEXT NOT NULL,
    supporting_evidence_json TEXT NOT NULL DEFAULT '[]',
    last_used_date TEXT,
    effectiveness_rating INTEGER,
    tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_objections_area ON objections(issue_area);
CREATE INDEX IF NOT EXISTS idx_objections_source ON objections(source_type);
CREATE INDEX IF NOT EXISTS idx_objections_rating ON objections(effectiveness_rating DESC);

-- ============================================================================
-- BATTLEFIELD DASHBOARD (DELTA COMMAND)
-- ============================================================================

CREATE TABLE IF NOT EXISTS bf_vehicles (
    vehicle_id TEXT PRIMARY KEY,
    vehicle_type TEXT NOT NULL,
    title TEXT NOT NULL,
    identifier TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    status_date TEXT NOT NULL,
    status_text TEXT,
    our_posture TEXT NOT NULL DEFAULT 'monitor',
    attack_surface TEXT,
    owner_internal TEXT,
    lobbyist_task TEXT,
    heat_score REAL,
    evidence_pack_id TEXT,
    last_action TEXT,
    last_action_date TEXT,
    source_type TEXT,
    source_id TEXT,
    source_url TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bf_vehicles_type ON bf_vehicles(vehicle_type);
CREATE INDEX IF NOT EXISTS idx_bf_vehicles_stage ON bf_vehicles(current_stage);
CREATE INDEX IF NOT EXISTS idx_bf_vehicles_posture ON bf_vehicles(our_posture);
CREATE INDEX IF NOT EXISTS idx_bf_vehicles_heat ON bf_vehicles(heat_score DESC);
CREATE INDEX IF NOT EXISTS idx_bf_vehicles_source ON bf_vehicles(source_type, source_id);

CREATE TABLE IF NOT EXISTS bf_calendar_events (
    event_id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    date TEXT NOT NULL,
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    time TEXT,
    location TEXT,
    importance TEXT NOT NULL DEFAULT 'watch',
    prep_required TEXT,
    source_type TEXT,
    source_id TEXT,
    passed INTEGER DEFAULT 0,
    cancelled INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (vehicle_id) REFERENCES bf_vehicles(vehicle_id)
);

CREATE INDEX IF NOT EXISTS idx_bf_calendar_date ON bf_calendar_events(date);
CREATE INDEX IF NOT EXISTS idx_bf_calendar_vehicle ON bf_calendar_events(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_bf_calendar_type ON bf_calendar_events(event_type);
CREATE INDEX IF NOT EXISTS idx_bf_calendar_importance ON bf_calendar_events(importance);
CREATE INDEX IF NOT EXISTS idx_bf_calendar_source ON bf_calendar_events(source_type, source_id);

CREATE TABLE IF NOT EXISTS bf_gate_alerts (
    alert_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    vehicle_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT NOT NULL,
    days_impact INTEGER,
    recommended_action TEXT,
    acknowledged INTEGER DEFAULT 0,
    acknowledged_by TEXT,
    acknowledged_at TEXT,
    source_event_id TEXT,
    source_type TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (vehicle_id) REFERENCES bf_vehicles(vehicle_id)
);

CREATE INDEX IF NOT EXISTS idx_bf_alerts_timestamp ON bf_gate_alerts(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_bf_alerts_vehicle ON bf_gate_alerts(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_bf_alerts_type ON bf_gate_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_bf_alerts_ack ON bf_gate_alerts(acknowledged);

CREATE TABLE IF NOT EXISTS bf_vehicle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    is_next_gate INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (vehicle_id) REFERENCES bf_vehicles(vehicle_id),
    FOREIGN KEY (event_id) REFERENCES bf_calendar_events(event_id),
    UNIQUE(vehicle_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_bf_ve_vehicle ON bf_vehicle_events(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_bf_ve_next ON bf_vehicle_events(is_next_gate);

CREATE TABLE IF NOT EXISTS bf_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    total_vehicles INTEGER NOT NULL,
    total_critical_gates INTEGER NOT NULL,
    total_alerts_24h INTEGER NOT NULL,
    by_type_json TEXT NOT NULL,
    by_posture_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bf_snapshots_date ON bf_snapshots(snapshot_date);

-- ============================================================================
-- AUTHENTICATION (ECHO COMMAND)
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at TEXT DEFAULT (datetime('now')),
    last_login TEXT,
    is_active INTEGER DEFAULT 1,
    created_by TEXT,
    CONSTRAINT valid_role CHECK (role IN ('commander', 'leadership', 'analyst', 'viewer'))
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    is_valid INTEGER DEFAULT 1,
    invalidated_at TEXT,
    invalidated_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id TEXT PRIMARY KEY,
    timestamp TEXT DEFAULT (datetime('now')),
    user_id TEXT,
    user_email TEXT,
    action TEXT NOT NULL,
    resource TEXT,
    resource_id TEXT,
    request_method TEXT,
    request_path TEXT,
    request_body TEXT,
    response_status INTEGER,
    ip_address TEXT,
    user_agent TEXT,
    duration_ms INTEGER,
    success INTEGER
);

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_email, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_success ON audit_log(success, timestamp);

-- Seed commander account
INSERT OR IGNORE INTO users (user_id, email, display_name, role, is_active)
VALUES ('pending-commander', 'x_aguiar@yahoo.com', 'Xavier Aguiar', 'commander', 1);

-- ============================================================================
-- CEO BRIEF (ALPHA COMMAND)
-- ============================================================================

CREATE TABLE IF NOT EXISTS ceo_briefs (
    brief_id TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    objective TEXT NOT NULL,
    content_json TEXT NOT NULL,
    markdown_output TEXT NOT NULL,
    validation_errors TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================================
-- TREND ANALYSIS (Historical Aggregations)
-- ============================================================================

-- Daily signal counts by trigger
CREATE TABLE IF NOT EXISTS trend_daily_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    trigger_id TEXT NOT NULL,
    signal_count INTEGER NOT NULL DEFAULT 0,
    suppressed_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, trigger_id)
);

CREATE INDEX IF NOT EXISTS idx_trend_daily_signals_date ON trend_daily_signals(date);
CREATE INDEX IF NOT EXISTS idx_trend_daily_signals_trigger ON trend_daily_signals(trigger_id);

-- Daily source health metrics
CREATE TABLE IF NOT EXISTS trend_daily_source_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    source_id TEXT NOT NULL,
    run_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    no_data_count INTEGER NOT NULL DEFAULT 0,
    total_docs INTEGER NOT NULL DEFAULT 0,
    success_rate REAL,
    avg_duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, source_id)
);

CREATE INDEX IF NOT EXISTS idx_trend_source_health_date ON trend_daily_source_health(date);
CREATE INDEX IF NOT EXISTS idx_trend_source_health_source ON trend_daily_source_health(source_id);

-- Weekly oversight summary
CREATE TABLE IF NOT EXISTS trend_weekly_oversight (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    total_events INTEGER NOT NULL DEFAULT 0,
    escalations INTEGER NOT NULL DEFAULT 0,
    deviations INTEGER NOT NULL DEFAULT 0,
    by_source_json TEXT NOT NULL DEFAULT '{}',
    by_theme_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(week_start)
);

CREATE INDEX IF NOT EXISTS idx_trend_weekly_oversight_week ON trend_weekly_oversight(week_start);

-- Daily battlefield snapshot
CREATE TABLE IF NOT EXISTS trend_daily_battlefield (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    total_vehicles INTEGER NOT NULL DEFAULT 0,
    active_vehicles INTEGER NOT NULL DEFAULT 0,
    critical_gates INTEGER NOT NULL DEFAULT 0,
    alerts_count INTEGER NOT NULL DEFAULT 0,
    by_type_json TEXT NOT NULL DEFAULT '{}',
    by_posture_json TEXT NOT NULL DEFAULT '{}',
    by_stage_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date)
);

CREATE INDEX IF NOT EXISTS idx_trend_daily_battlefield_date ON trend_daily_battlefield(date);

-- ============================================================
-- LDA.gov Lobbying Disclosure Filings
-- ============================================================

CREATE TABLE IF NOT EXISTS lda_filings (
    filing_uuid TEXT PRIMARY KEY,
    filing_type TEXT NOT NULL,
    filing_year INTEGER,
    filing_period TEXT,
    dt_posted TEXT NOT NULL,
    registrant_name TEXT NOT NULL,
    registrant_id TEXT,
    client_name TEXT NOT NULL,
    client_id TEXT,
    income_amount REAL,
    expense_amount REAL,
    lobbying_issues_json TEXT,
    specific_issues_text TEXT,
    govt_entities_json TEXT,
    lobbyists_json TEXT,
    foreign_entity_listed INTEGER DEFAULT 0,
    foreign_entities_json TEXT,
    covered_positions_json TEXT,
    source_url TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    updated_at TEXT,
    va_relevance_score TEXT DEFAULT 'LOW',
    va_relevance_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_lda_filings_posted ON lda_filings(dt_posted);
CREATE INDEX IF NOT EXISTS idx_lda_filings_type ON lda_filings(filing_type);
CREATE INDEX IF NOT EXISTS idx_lda_filings_relevance ON lda_filings(va_relevance_score);

CREATE TABLE IF NOT EXISTS lda_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filing_uuid TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    summary TEXT NOT NULL,
    details_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    acknowledged INTEGER DEFAULT 0,
    FOREIGN KEY (filing_uuid) REFERENCES lda_filings(filing_uuid)
);

CREATE INDEX IF NOT EXISTS idx_lda_alerts_severity ON lda_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_lda_alerts_filing ON lda_alerts(filing_uuid);
