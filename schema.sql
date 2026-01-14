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
