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
