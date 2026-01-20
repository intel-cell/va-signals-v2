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
