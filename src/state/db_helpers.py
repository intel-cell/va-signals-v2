"""Database helpers for state intelligence module."""

from datetime import UTC, datetime

from src.db import connect, execute, insert_returning_id

# Default sources for TX, CA, FL, PA, OH, NY, NC, GA, VA, AZ
DEFAULT_SOURCES = [
    # Texas
    {
        "source_id": "tx_tvc_news",
        "state": "TX",
        "source_type": "official",
        "name": "Texas Veterans Commission News",
        "url": "https://tvc.texas.gov/news",
    },
    {
        "source_id": "tx_register",
        "state": "TX",
        "source_type": "official",
        "name": "Texas Register",
        "url": "https://texreg.sos.state.tx.us",
    },
    # California
    {
        "source_id": "ca_calvet_news",
        "state": "CA",
        "source_type": "official",
        "name": "CalVet Newsroom",
        "url": "https://calvet.ca.gov/news",
    },
    {
        "source_id": "ca_oal_register",
        "state": "CA",
        "source_type": "official",
        "name": "OAL Notice Register",
        "url": "https://oal.ca.gov/publications",
    },
    # Florida
    {
        "source_id": "fl_dva_news",
        "state": "FL",
        "source_type": "official",
        "name": "Florida DVA News",
        "url": "https://floridavets.org/news",
    },
    {
        "source_id": "fl_admin_register",
        "state": "FL",
        "source_type": "official",
        "name": "Florida Administrative Register",
        "url": "https://flrules.org",
    },
    # Pennsylvania
    {
        "source_id": "pa_dmva_news",
        "state": "PA",
        "source_type": "official",
        "name": "PA DMVA Press Releases",
        "url": "https://www.pa.gov/agencies/dmva/",
    },
    # Ohio
    {
        "source_id": "oh_odvs_news",
        "state": "OH",
        "source_type": "official",
        "name": "Ohio DVS News",
        "url": "https://dvs.ohio.gov/news-and-events",
    },
    # New York
    {
        "source_id": "ny_dvs_news",
        "state": "NY",
        "source_type": "official",
        "name": "NY DVS Pressroom",
        "url": "https://veterans.ny.gov/pressroom",
    },
    # North Carolina
    {
        "source_id": "nc_dmva_news",
        "state": "NC",
        "source_type": "official",
        "name": "NC DMVA Press Releases",
        "url": "https://www.milvets.nc.gov/news/press-releases",
    },
    # Georgia
    {
        "source_id": "ga_dvs_news",
        "state": "GA",
        "source_type": "official",
        "name": "GA DVS Press Releases",
        "url": "https://veterans.georgia.gov/press-releases",
    },
    # Virginia
    {
        "source_id": "va_dvs_news",
        "state": "VA",
        "source_type": "official",
        "name": "Virginia DVS News",
        "url": "https://www.dvs.virginia.gov/news-room/press-release",
    },
    # Arizona
    {
        "source_id": "az_dvs_news",
        "state": "AZ",
        "source_type": "official",
        "name": "Arizona DVS Press Releases",
        "url": "https://dvs.az.gov/press-releases",
    },
    # RSS Feeds
    {
        "source_id": "rss_texas_tribune",
        "state": "TX",
        "source_type": "rss",
        "name": "Texas Tribune",
        "url": "https://www.texastribune.org/feeds/rss/",
    },
    {
        "source_id": "rss_calmatters",
        "state": "CA",
        "source_type": "rss",
        "name": "CalMatters",
        "url": "https://calmatters.org/feed/",
    },
    {
        "source_id": "rss_florida_phoenix",
        "state": "FL",
        "source_type": "rss",
        "name": "Florida Phoenix",
        "url": "https://floridaphoenix.com/feed/",
    },
    {
        "source_id": "rss_pennlive",
        "state": "PA",
        "source_type": "rss",
        "name": "PennLive",
        "url": "https://www.pennlive.com/arc/outboundfeeds/rss/?outputType=xml",
    },
    {
        "source_id": "rss_columbus_dispatch",
        "state": "OH",
        "source_type": "rss",
        "name": "Columbus Dispatch",
        "url": "https://www.dispatch.com/arcio/rss/category/news/",
    },
    {
        "source_id": "rss_times_union",
        "state": "NY",
        "source_type": "rss",
        "name": "Times Union Albany",
        "url": "https://www.timesunion.com/news/rss/feed/",
    },
    {
        "source_id": "rss_charlotte_observer",
        "state": "NC",
        "source_type": "rss",
        "name": "Charlotte Observer",
        "url": "https://www.charlotteobserver.com/news/politics-government/rss.xml",
    },
    {
        "source_id": "rss_ajc",
        "state": "GA",
        "source_type": "rss",
        "name": "Atlanta Journal-Constitution",
        "url": "https://www.ajc.com/arcio/rss/category/news/",
    },
    {
        "source_id": "rss_richmond_td",
        "state": "VA",
        "source_type": "rss",
        "name": "Richmond Times-Dispatch",
        "url": "https://richmond.com/search/?f=rss&t=article&c=news&l=50&s=start_time&sd=desc",
    },
    {
        "source_id": "rss_az_central",
        "state": "AZ",
        "source_type": "rss",
        "name": "AZ Central",
        "url": "https://rssfeeds.azcentral.com/phoenix/news",
    },
]


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()


# --- Source helpers ---


def insert_state_source(source: dict) -> None:
    """
    Insert a state source (idempotent - skips if already exists).
    Expected keys: source_id, state, source_type, name, url, enabled (optional).
    """
    con = connect()
    execute(
        con,
        """INSERT INTO state_sources(source_id, state, source_type, name, url, enabled, created_at)
           VALUES(:source_id, :state, :source_type, :name, :url, :enabled, :created_at)
           ON CONFLICT(source_id) DO NOTHING""",
        {
            "source_id": source["source_id"],
            "state": source["state"],
            "source_type": source["source_type"],
            "name": source["name"],
            "url": source["url"],
            "enabled": source.get("enabled", 1),
            "created_at": _utc_now_iso(),
        },
    )
    con.commit()
    con.close()


def get_state_source(source_id: str) -> dict | None:
    """Get a source by ID."""
    con = connect()
    cur = execute(
        con,
        """SELECT source_id, state, source_type, name, url, enabled, created_at
           FROM state_sources WHERE source_id = :source_id""",
        {"source_id": source_id},
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
    if enabled_only:
        cur = execute(
            con,
            """SELECT source_id, state, source_type, name, url, enabled, created_at
               FROM state_sources WHERE state = :state AND enabled = 1
               ORDER BY source_type, name""",
            {"state": state},
        )
    else:
        cur = execute(
            con,
            """SELECT source_id, state, source_type, name, url, enabled, created_at
               FROM state_sources WHERE state = :state
               ORDER BY source_type, name""",
            {"state": state},
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


def insert_state_signal(signal: dict) -> None:
    """
    Insert a state signal (idempotent - skips if already exists).
    Expected keys: signal_id, state, source_id, title, url.
    Optional: program, content, pub_date, event_date.
    """
    con = connect()
    execute(
        con,
        """INSERT INTO state_signals(
               signal_id, state, source_id, program, title, content, url, pub_date, event_date, fetched_at
           ) VALUES (
               :signal_id, :state, :source_id, :program, :title, :content, :url, :pub_date, :event_date, :fetched_at
           ) ON CONFLICT(signal_id) DO NOTHING""",
        {
            "signal_id": signal["signal_id"],
            "state": signal["state"],
            "source_id": signal["source_id"],
            "program": signal.get("program"),
            "title": signal["title"],
            "content": signal.get("content"),
            "url": signal["url"],
            "pub_date": signal.get("pub_date"),
            "event_date": signal.get("event_date"),
            "fetched_at": _utc_now_iso(),
        },
    )
    con.commit()
    con.close()


def get_state_signal(signal_id: str) -> dict | None:
    """Get a signal by ID."""
    con = connect()
    cur = execute(
        con,
        """SELECT id, signal_id, state, source_id, program, title, content, url, pub_date, event_date, fetched_at
           FROM state_signals WHERE signal_id = :signal_id""",
        {"signal_id": signal_id},
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
    cur = execute(
        con,
        "SELECT 1 FROM state_signals WHERE signal_id = :signal_id",
        {"signal_id": signal_id},
    )
    exists = cur.fetchone() is not None
    con.close()
    return exists


def get_signals_by_state(state: str, since: str | None = None, limit: int = 100) -> list[dict]:
    """Get signals for a state, ordered by pub_date descending.

    If `since` is provided, filter by fetched_at >= since.
    """
    con = connect()
    if since:
        cur = execute(
            con,
            """SELECT id, signal_id, state, source_id, program, title, content, url, pub_date, event_date, fetched_at
               FROM state_signals WHERE state = :state AND fetched_at >= :since
               ORDER BY pub_date DESC, fetched_at DESC LIMIT :limit""",
            {"state": state, "since": since, "limit": limit},
        )
    else:
        cur = execute(
            con,
            """SELECT id, signal_id, state, source_id, program, title, content, url, pub_date, event_date, fetched_at
               FROM state_signals WHERE state = :state
               ORDER BY pub_date DESC, fetched_at DESC LIMIT :limit""",
            {"state": state, "limit": limit},
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


def insert_state_classification(classification: dict) -> None:
    """
    Insert a classification for a signal (idempotent - skips if already exists).
    Expected keys: signal_id, severity, classification_method.
    Optional: keywords_matched, llm_reasoning.
    """
    con = connect()
    execute(
        con,
        """INSERT INTO state_classifications(
               signal_id, severity, classification_method, keywords_matched, llm_reasoning, classified_at
           ) VALUES (
               :signal_id, :severity, :classification_method, :keywords_matched, :llm_reasoning, :classified_at
           ) ON CONFLICT(signal_id) DO NOTHING""",
        {
            "signal_id": classification["signal_id"],
            "severity": classification["severity"],
            "classification_method": classification["classification_method"],
            "keywords_matched": classification.get("keywords_matched"),
            "llm_reasoning": classification.get("llm_reasoning"),
            "classified_at": _utc_now_iso(),
        },
    )
    con.commit()
    con.close()


def get_state_classification(signal_id: str) -> dict | None:
    """Get classification for a signal."""
    con = connect()
    cur = execute(
        con,
        """SELECT signal_id, severity, classification_method, keywords_matched, llm_reasoning, classified_at
           FROM state_classifications WHERE signal_id = :signal_id""",
        {"signal_id": signal_id},
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


def get_unnotified_signals(severity: str | None = None, limit: int = 100) -> list[dict]:
    """
    Get signals that have been classified but not notified.
    Optionally filter by severity.
    """
    con = connect()
    if severity:
        cur = execute(
            con,
            """SELECT s.signal_id, s.state, s.source_id, s.title, s.url, s.pub_date,
                      c.severity, c.classification_method, c.classified_at
               FROM state_signals s
               JOIN state_classifications c ON s.signal_id = c.signal_id
               LEFT JOIN state_notifications n ON s.signal_id = n.signal_id
               WHERE n.signal_id IS NULL AND c.severity = :severity
               ORDER BY c.classified_at DESC LIMIT :limit""",
            {"severity": severity, "limit": limit},
        )
    else:
        cur = execute(
            con,
            """SELECT s.signal_id, s.state, s.source_id, s.title, s.url, s.pub_date,
                      c.severity, c.classification_method, c.classified_at
               FROM state_signals s
               JOIN state_classifications c ON s.signal_id = c.signal_id
               LEFT JOIN state_notifications n ON s.signal_id = n.signal_id
               WHERE n.signal_id IS NULL
               ORDER BY c.classified_at DESC LIMIT :limit""",
            {"limit": limit},
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


def mark_signal_notified(signal_id: str, channel: str) -> None:
    """
    Mark a signal as notified (idempotent - skips if already exists).
    """
    con = connect()
    execute(
        con,
        """
        INSERT INTO state_notifications (signal_id, notified_at, channel)
        VALUES (:signal_id, :notified_at, :channel)
        ON CONFLICT(signal_id) DO NOTHING
        """,
        {"signal_id": signal_id, "notified_at": _utc_now_iso(), "channel": channel},
    )
    con.commit()
    con.close()


# --- Run tracking ---


def start_state_run(run_type: str, state: str = None) -> int:
    """
    Start a state run. Returns the run ID.
    run_type: 'fetch', 'classify', 'notify', etc.
    """
    con = connect()
    run_id = insert_returning_id(
        con,
        """INSERT INTO state_runs(run_type, state, status, signals_found, high_severity_count, started_at)
           VALUES(:run_type, :state, :status, :signals_found, :high_severity_count, :started_at)""",
        {
            "run_type": run_type,
            "state": state,
            "status": "RUNNING",
            "signals_found": 0,
            "high_severity_count": 0,
            "started_at": _utc_now_iso(),
        },
    )
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
    execute(
        con,
        """UPDATE state_runs
           SET status=:status, signals_found=:signals_found, high_severity_count=:high_severity_count, finished_at=:finished_at
           WHERE id=:run_id""",
        {
            "status": status,
            "signals_found": signals_found,
            "high_severity_count": high_severity_count,
            "finished_at": _utc_now_iso(),
            "run_id": run_id,
        },
    )
    con.commit()
    con.close()


def get_recent_state_runs(limit: int = 20, state: str = None, run_type: str = None) -> list[dict]:
    """Get recent state runs, optionally filtered."""
    con = connect()

    query = """SELECT id, run_type, state, status, signals_found, high_severity_count, started_at, finished_at
               FROM state_runs WHERE 1=1"""
    params: dict[str, object] = {}

    if state:
        query += " AND state = :state"
        params["state"] = state
    if run_type:
        query += " AND run_type = :run_type"
        params["run_type"] = run_type

    query += " ORDER BY started_at DESC LIMIT :limit"
    params["limit"] = limit

    cur = execute(con, query, params)
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


# Alias for dashboard API compatibility
get_recent_runs = get_recent_state_runs


def get_signal_count_by_state() -> dict[str, int]:
    """Get count of signals grouped by state."""
    con = connect()
    cur = execute(con, "SELECT state, COUNT(*) FROM state_signals GROUP BY state")
    rows = cur.fetchall()
    con.close()
    return {r[0]: r[1] for r in rows}


def get_signal_count_by_severity() -> dict[str, int]:
    """Get count of signals grouped by severity."""
    con = connect()
    cur = execute(
        con,
        """SELECT c.severity, COUNT(*)
           FROM state_classifications c
           GROUP BY c.severity""",
    )
    rows = cur.fetchall()
    con.close()
    return {r[0]: r[1] for r in rows}


def get_latest_run() -> dict | None:
    """Get the most recent state run."""
    con = connect()
    cur = execute(
        con,
        """SELECT id, run_type, state, status, signals_found, high_severity_count, started_at, finished_at
           FROM state_runs ORDER BY started_at DESC LIMIT 1""",
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "id": row[0],
        "run_type": row[1],
        "state": row[2],
        "status": row[3],
        "signals_found": row[4],
        "high_severity_count": row[5],
        "started_at": row[6],
        "finished_at": row[7],
    }


# --- Source health tracking ---


def update_source_health(source_id: str, success: bool, error: str = None) -> None:
    """
    Update health tracking for a source using atomic UPSERT.
    On success: reset consecutive_failures, update last_success.
    On failure: increment consecutive_failures, update last_failure and last_error.
    """
    con = connect()
    now = _utc_now_iso()

    if success:
        execute(
            con,
            """INSERT INTO state_source_health(source_id, consecutive_failures, last_success)
               VALUES(:source_id, 0, :now)
               ON CONFLICT(source_id) DO UPDATE SET
                   consecutive_failures = 0,
                   last_success = :now""",
            {"source_id": source_id, "now": now},
        )
    else:
        execute(
            con,
            """INSERT INTO state_source_health(source_id, consecutive_failures, last_failure, last_error)
               VALUES(:source_id, 1, :now, :error)
               ON CONFLICT(source_id) DO UPDATE SET
                   consecutive_failures = state_source_health.consecutive_failures + 1,
                   last_failure = :now,
                   last_error = :error""",
            {"source_id": source_id, "now": now, "error": error},
        )

    con.commit()
    con.close()


def get_source_health(source_id: str) -> dict | None:
    """Get health status for a source."""
    con = connect()
    cur = execute(
        con,
        """SELECT source_id, consecutive_failures, last_success, last_failure, last_error
           FROM state_source_health WHERE source_id = :source_id""",
        {"source_id": source_id},
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
        # Check if exists before inserting
        if get_state_source(source["source_id"]) is None:
            insert_state_source(source)
            count += 1
    return count
