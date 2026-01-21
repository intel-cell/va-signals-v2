"""Database helpers for state intelligence module."""

from datetime import datetime, timezone

from src.db import connect


# Default sources for TX, CA, FL
DEFAULT_SOURCES = [
    # Texas
    {
        "source_id": "tx_tvc_official",
        "state": "TX",
        "source_type": "official",
        "name": "Texas Veterans Commission",
        "url": "https://www.tvc.texas.gov/",
    },
    {
        "source_id": "tx_tvc_news",
        "state": "TX",
        "source_type": "rss",
        "name": "Texas Veterans Commission News",
        "url": "https://www.tvc.texas.gov/feed/",
    },
    {
        "source_id": "tx_gov_news",
        "state": "TX",
        "source_type": "rss",
        "name": "Texas Governor Veterans News",
        "url": "https://gov.texas.gov/news/category/veterans",
    },
    # California
    {
        "source_id": "ca_calvet_official",
        "state": "CA",
        "source_type": "official",
        "name": "California Department of Veterans Affairs",
        "url": "https://www.calvet.ca.gov/",
    },
    {
        "source_id": "ca_calvet_news",
        "state": "CA",
        "source_type": "rss",
        "name": "CalVet News",
        "url": "https://www.calvet.ca.gov/Pages/News.aspx",
    },
    {
        "source_id": "ca_legislature",
        "state": "CA",
        "source_type": "official",
        "name": "California Legislature Veterans Affairs",
        "url": "https://leginfo.legislature.ca.gov/",
    },
    # Florida
    {
        "source_id": "fl_fdva_official",
        "state": "FL",
        "source_type": "official",
        "name": "Florida Department of Veterans Affairs",
        "url": "https://www.floridavets.org/",
    },
    {
        "source_id": "fl_fdva_news",
        "state": "FL",
        "source_type": "rss",
        "name": "FDVA News",
        "url": "https://www.floridavets.org/news/",
    },
    {
        "source_id": "fl_gov_news",
        "state": "FL",
        "source_type": "rss",
        "name": "Florida Governor Veterans News",
        "url": "https://www.flgov.com/category/veterans/",
    },
]


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# --- Source helpers ---


def insert_state_source(source: dict) -> bool:
    """
    Insert a state source. Returns True if new (inserted), False if already exists.
    Expected keys: source_id, state, source_type, name, url, enabled (optional).
    """
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT source_id FROM state_sources WHERE source_id = ?", (source["source_id"],))
    if cur.fetchone() is not None:
        con.close()
        return False

    cur.execute(
        """INSERT INTO state_sources(source_id, state, source_type, name, url, enabled, created_at)
           VALUES(?,?,?,?,?,?,?)""",
        (
            source["source_id"],
            source["state"],
            source["source_type"],
            source["name"],
            source["url"],
            source.get("enabled", 1),
            _utc_now_iso(),
        ),
    )
    con.commit()
    con.close()
    return True


def get_state_source(source_id: str) -> dict | None:
    """Get a source by ID."""
    con = connect()
    cur = con.cursor()
    cur.execute(
        """SELECT source_id, state, source_type, name, url, enabled, created_at
           FROM state_sources WHERE source_id = ?""",
        (source_id,),
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "source_id": row[0],
        "state": row[1],
        "source_type": row[2],
        "name": row[3],
        "url": row[4],
        "enabled": row[5],
        "created_at": row[6],
    }


def get_sources_by_state(state: str, enabled_only: bool = True) -> list[dict]:
    """Get all sources for a state."""
    con = connect()
    cur = con.cursor()
    if enabled_only:
        cur.execute(
            """SELECT source_id, state, source_type, name, url, enabled, created_at
               FROM state_sources WHERE state = ? AND enabled = 1
               ORDER BY source_type, name""",
            (state,),
        )
    else:
        cur.execute(
            """SELECT source_id, state, source_type, name, url, enabled, created_at
               FROM state_sources WHERE state = ?
               ORDER BY source_type, name""",
            (state,),
        )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "source_id": r[0],
            "state": r[1],
            "source_type": r[2],
            "name": r[3],
            "url": r[4],
            "enabled": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


# --- Signal helpers ---


def insert_state_signal(signal: dict) -> bool:
    """
    Insert a state signal. Returns True if new (inserted), False if already exists.
    Expected keys: signal_id, state, source_id, title, url.
    Optional: program, content, pub_date, event_date.
    """
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT signal_id FROM state_signals WHERE signal_id = ?", (signal["signal_id"],))
    if cur.fetchone() is not None:
        con.close()
        return False

    cur.execute(
        """INSERT INTO state_signals(signal_id, state, source_id, program, title, content, url, pub_date, event_date, fetched_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            signal["signal_id"],
            signal["state"],
            signal["source_id"],
            signal.get("program"),
            signal["title"],
            signal.get("content"),
            signal["url"],
            signal.get("pub_date"),
            signal.get("event_date"),
            _utc_now_iso(),
        ),
    )
    con.commit()
    con.close()
    return True


def get_state_signal(signal_id: str) -> dict | None:
    """Get a signal by ID."""
    con = connect()
    cur = con.cursor()
    cur.execute(
        """SELECT id, signal_id, state, source_id, program, title, content, url, pub_date, event_date, fetched_at
           FROM state_signals WHERE signal_id = ?""",
        (signal_id,),
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "id": row[0],
        "signal_id": row[1],
        "state": row[2],
        "source_id": row[3],
        "program": row[4],
        "title": row[5],
        "content": row[6],
        "url": row[7],
        "pub_date": row[8],
        "event_date": row[9],
        "fetched_at": row[10],
    }


def signal_exists(signal_id: str) -> bool:
    """Check if a signal exists."""
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT 1 FROM state_signals WHERE signal_id = ?", (signal_id,))
    exists = cur.fetchone() is not None
    con.close()
    return exists


def get_signals_by_state(state: str, limit: int = 100) -> list[dict]:
    """Get signals for a state, ordered by pub_date descending."""
    con = connect()
    cur = con.cursor()
    cur.execute(
        """SELECT id, signal_id, state, source_id, program, title, content, url, pub_date, event_date, fetched_at
           FROM state_signals WHERE state = ?
           ORDER BY pub_date DESC, fetched_at DESC LIMIT ?""",
        (state, limit),
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r[0],
            "signal_id": r[1],
            "state": r[2],
            "source_id": r[3],
            "program": r[4],
            "title": r[5],
            "content": r[6],
            "url": r[7],
            "pub_date": r[8],
            "event_date": r[9],
            "fetched_at": r[10],
        }
        for r in rows
    ]


# --- Classification helpers ---


def insert_state_classification(classification: dict) -> bool:
    """
    Insert a classification for a signal. Returns True if new.
    Expected keys: signal_id, severity, classification_method.
    Optional: keywords_matched, llm_reasoning.
    """
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT signal_id FROM state_classifications WHERE signal_id = ?", (classification["signal_id"],))
    if cur.fetchone() is not None:
        con.close()
        return False

    cur.execute(
        """INSERT INTO state_classifications(signal_id, severity, classification_method, keywords_matched, llm_reasoning, classified_at)
           VALUES(?,?,?,?,?,?)""",
        (
            classification["signal_id"],
            classification["severity"],
            classification["classification_method"],
            classification.get("keywords_matched"),
            classification.get("llm_reasoning"),
            _utc_now_iso(),
        ),
    )
    con.commit()
    con.close()
    return True


def get_state_classification(signal_id: str) -> dict | None:
    """Get classification for a signal."""
    con = connect()
    cur = con.cursor()
    cur.execute(
        """SELECT signal_id, severity, classification_method, keywords_matched, llm_reasoning, classified_at
           FROM state_classifications WHERE signal_id = ?""",
        (signal_id,),
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "signal_id": row[0],
        "severity": row[1],
        "classification_method": row[2],
        "keywords_matched": row[3],
        "llm_reasoning": row[4],
        "classified_at": row[5],
    }


def get_unnotified_signals(severity: str = None, limit: int = 100) -> list[dict]:
    """
    Get signals that have been classified but not notified.
    Optionally filter by severity.
    """
    con = connect()
    cur = con.cursor()
    if severity:
        cur.execute(
            """SELECT s.signal_id, s.state, s.source_id, s.title, s.url, s.pub_date,
                      c.severity, c.classification_method, c.classified_at
               FROM state_signals s
               JOIN state_classifications c ON s.signal_id = c.signal_id
               LEFT JOIN state_notifications n ON s.signal_id = n.signal_id
               WHERE n.signal_id IS NULL AND c.severity = ?
               ORDER BY c.classified_at DESC LIMIT ?""",
            (severity, limit),
        )
    else:
        cur.execute(
            """SELECT s.signal_id, s.state, s.source_id, s.title, s.url, s.pub_date,
                      c.severity, c.classification_method, c.classified_at
               FROM state_signals s
               JOIN state_classifications c ON s.signal_id = c.signal_id
               LEFT JOIN state_notifications n ON s.signal_id = n.signal_id
               WHERE n.signal_id IS NULL
               ORDER BY c.classified_at DESC LIMIT ?""",
            (limit,),
        )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "signal_id": r[0],
            "state": r[1],
            "source_id": r[2],
            "title": r[3],
            "url": r[4],
            "pub_date": r[5],
            "severity": r[6],
            "classification_method": r[7],
            "classified_at": r[8],
        }
        for r in rows
    ]


def mark_signal_notified(signal_id: str, channel: str) -> bool:
    """
    Mark a signal as notified. Returns True if successfully inserted.
    """
    con = connect()
    cur = con.cursor()
    try:
        cur.execute(
            """INSERT INTO state_notifications(signal_id, notified_at, channel) VALUES(?,?,?)""",
            (signal_id, _utc_now_iso(), channel),
        )
        con.commit()
        con.close()
        return True
    except Exception:
        con.close()
        return False


# --- Run tracking ---


def start_state_run(run_type: str, state: str = None) -> int:
    """
    Start a state run. Returns the run ID.
    run_type: 'fetch', 'classify', 'notify', etc.
    """
    con = connect()
    cur = con.cursor()
    cur.execute(
        """INSERT INTO state_runs(run_type, state, status, signals_found, high_severity_count, started_at)
           VALUES(?,?,?,?,?,?)""",
        (run_type, state, "RUNNING", 0, 0, _utc_now_iso()),
    )
    run_id = cur.lastrowid
    con.commit()
    con.close()
    return run_id


def finish_state_run(
    run_id: int,
    status: str,
    signals_found: int = 0,
    high_severity_count: int = 0,
) -> None:
    """Finish a state run with final stats."""
    con = connect()
    cur = con.cursor()
    cur.execute(
        """UPDATE state_runs SET status=?, signals_found=?, high_severity_count=?, finished_at=?
           WHERE id=?""",
        (status, signals_found, high_severity_count, _utc_now_iso(), run_id),
    )
    con.commit()
    con.close()


def get_recent_state_runs(limit: int = 20, state: str = None, run_type: str = None) -> list[dict]:
    """Get recent state runs, optionally filtered."""
    con = connect()
    cur = con.cursor()

    query = """SELECT id, run_type, state, status, signals_found, high_severity_count, started_at, finished_at
               FROM state_runs WHERE 1=1"""
    params = []

    if state:
        query += " AND state = ?"
        params.append(state)
    if run_type:
        query += " AND run_type = ?"
        params.append(run_type)

    query += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)

    cur.execute(query, params)
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r[0],
            "run_type": r[1],
            "state": r[2],
            "status": r[3],
            "signals_found": r[4],
            "high_severity_count": r[5],
            "started_at": r[6],
            "finished_at": r[7],
        }
        for r in rows
    ]


# --- Source health tracking ---


def update_source_health(source_id: str, success: bool, error: str = None) -> None:
    """
    Update health tracking for a source.
    On success: reset consecutive_failures, update last_success.
    On failure: increment consecutive_failures, update last_failure and last_error.
    """
    con = connect()
    cur = con.cursor()
    now = _utc_now_iso()

    # Check if record exists
    cur.execute("SELECT source_id FROM state_source_health WHERE source_id = ?", (source_id,))
    exists = cur.fetchone() is not None

    if success:
        if exists:
            cur.execute(
                """UPDATE state_source_health SET consecutive_failures=0, last_success=?
                   WHERE source_id=?""",
                (now, source_id),
            )
        else:
            cur.execute(
                """INSERT INTO state_source_health(source_id, consecutive_failures, last_success)
                   VALUES(?,?,?)""",
                (source_id, 0, now),
            )
    else:
        if exists:
            cur.execute(
                """UPDATE state_source_health SET consecutive_failures = consecutive_failures + 1,
                   last_failure=?, last_error=?
                   WHERE source_id=?""",
                (now, error, source_id),
            )
        else:
            cur.execute(
                """INSERT INTO state_source_health(source_id, consecutive_failures, last_failure, last_error)
                   VALUES(?,?,?,?)""",
                (source_id, 1, now, error),
            )

    con.commit()
    con.close()


def get_source_health(source_id: str) -> dict | None:
    """Get health status for a source."""
    con = connect()
    cur = con.cursor()
    cur.execute(
        """SELECT source_id, consecutive_failures, last_success, last_failure, last_error
           FROM state_source_health WHERE source_id = ?""",
        (source_id,),
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "source_id": row[0],
        "consecutive_failures": row[1],
        "last_success": row[2],
        "last_failure": row[3],
        "last_error": row[4],
    }


# --- Seeding ---


def seed_default_sources() -> int:
    """
    Seed default sources for TX, CA, FL.
    Returns count of newly inserted sources.
    """
    count = 0
    for source in DEFAULT_SOURCES:
        if insert_state_source(source):
            count += 1
    return count
