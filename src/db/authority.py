"""Authority Docs database functions."""

from .core import connect, execute
from .helpers import _utc_now_iso


def upsert_authority_doc(doc: dict) -> bool:
    """
    Insert or update an authority document. Returns True if new or updated.

    Expected keys: doc_id, authority_source, authority_type, title, published_at,
    source_url, body_text, content_hash, metadata_json.
    """
    con = connect()
    now = _utc_now_iso()

    cur = execute(
        con,
        "SELECT doc_id, content_hash, version FROM authority_docs WHERE doc_id = :doc_id",
        {"doc_id": doc["doc_id"]},
    )
    existing = cur.fetchone()

    if existing is None:
        # New document - insert
        execute(
            con,
            """INSERT INTO authority_docs(
                 doc_id, authority_source, authority_type, title, published_at,
                 source_url, body_text, content_hash, version, metadata_json,
                 fetched_at, first_seen_at
               ) VALUES (
                 :doc_id, :authority_source, :authority_type, :title, :published_at,
                 :source_url, :body_text, :content_hash, :version, :metadata_json,
                 :fetched_at, :first_seen_at
               )""",
            {
                "doc_id": doc["doc_id"],
                "authority_source": doc["authority_source"],
                "authority_type": doc["authority_type"],
                "title": doc["title"],
                "published_at": doc.get("published_at"),
                "source_url": doc["source_url"],
                "body_text": doc.get("body_text"),
                "content_hash": doc.get("content_hash"),
                "version": 1,
                "metadata_json": doc.get("metadata_json"),
                "fetched_at": now,
                "first_seen_at": now,
            },
        )
        con.commit()
        con.close()
        return True

    # Check if content changed (by hash)
    old_hash = existing[1]
    old_version = existing[2] or 1
    new_hash = doc.get("content_hash")

    if old_hash != new_hash and new_hash is not None:
        # Content changed - update with incremented version
        execute(
            con,
            """UPDATE authority_docs
               SET authority_source=:authority_source, authority_type=:authority_type,
                   title=:title, published_at=:published_at, source_url=:source_url,
                   body_text=:body_text, content_hash=:content_hash, version=:version,
                   metadata_json=:metadata_json, fetched_at=:fetched_at, updated_at=:updated_at
               WHERE doc_id=:doc_id""",
            {
                "doc_id": doc["doc_id"],
                "authority_source": doc["authority_source"],
                "authority_type": doc["authority_type"],
                "title": doc["title"],
                "published_at": doc.get("published_at"),
                "source_url": doc["source_url"],
                "body_text": doc.get("body_text"),
                "content_hash": new_hash,
                "version": old_version + 1,
                "metadata_json": doc.get("metadata_json"),
                "fetched_at": now,
                "updated_at": now,
            },
        )
        con.commit()
        con.close()
        return True

    con.close()
    return False


def fetch_unrouted_authority_docs(limit: int = 100) -> list[dict]:
    """
    Fetch authority documents that haven't been routed yet (routed_at IS NULL).
    Returns list of dicts ordered by first_seen_at ascending.
    """
    con = connect()
    cur = execute(
        con,
        """SELECT doc_id, authority_source, authority_type, title, published_at,
                  source_url, body_text, content_hash, version, metadata_json,
                  fetched_at, first_seen_at, updated_at
           FROM authority_docs
           WHERE routed_at IS NULL
           ORDER BY first_seen_at ASC
           LIMIT :limit""",
        {"limit": limit},
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "doc_id": r[0],
            "authority_source": r[1],
            "authority_type": r[2],
            "title": r[3],
            "published_at": r[4],
            "source_url": r[5],
            "body_text": r[6],
            "content_hash": r[7],
            "version": r[8],
            "metadata_json": r[9],
            "fetched_at": r[10],
            "first_seen_at": r[11],
            "updated_at": r[12],
        }
        for r in rows
    ]


def mark_authority_doc_routed(doc_id: str, routed_via: str = None) -> None:
    """Mark an authority document as routed."""
    con = connect()
    now = _utc_now_iso()
    execute(
        con,
        "UPDATE authority_docs SET routed_at = :routed_at WHERE doc_id = :doc_id",
        {"doc_id": doc_id, "routed_at": now},
    )
    con.commit()
    con.close()


def get_authority_doc(doc_id: str) -> dict | None:
    """Get a single authority document by ID."""
    con = connect()
    cur = execute(
        con,
        """SELECT doc_id, authority_source, authority_type, title, published_at,
                  source_url, body_text, content_hash, version, metadata_json,
                  fetched_at, first_seen_at, updated_at, routed_at
           FROM authority_docs WHERE doc_id = :doc_id""",
        {"doc_id": doc_id},
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "doc_id": row[0],
        "authority_source": row[1],
        "authority_type": row[2],
        "title": row[3],
        "published_at": row[4],
        "source_url": row[5],
        "body_text": row[6],
        "content_hash": row[7],
        "version": row[8],
        "metadata_json": row[9],
        "fetched_at": row[10],
        "first_seen_at": row[11],
        "updated_at": row[12],
        "routed_at": row[13],
    }


def get_authority_docs(
    authority_source: str = None, limit: int = 50
) -> list[dict]:
    """Get authority documents, optionally filtered by source."""
    con = connect()

    if authority_source:
        cur = execute(
            con,
            """SELECT doc_id, authority_source, authority_type, title, published_at,
                      source_url, body_text, content_hash, version, metadata_json,
                      fetched_at, first_seen_at, updated_at, routed_at
               FROM authority_docs
               WHERE authority_source = :authority_source
               ORDER BY published_at DESC NULLS LAST
               LIMIT :limit""",
            {"authority_source": authority_source, "limit": limit},
        )
    else:
        cur = execute(
            con,
            """SELECT doc_id, authority_source, authority_type, title, published_at,
                      source_url, body_text, content_hash, version, metadata_json,
                      fetched_at, first_seen_at, updated_at, routed_at
               FROM authority_docs
               ORDER BY published_at DESC NULLS LAST
               LIMIT :limit""",
            {"limit": limit},
        )

    rows = cur.fetchall()
    con.close()
    return [
        {
            "doc_id": r[0],
            "authority_source": r[1],
            "authority_type": r[2],
            "title": r[3],
            "published_at": r[4],
            "source_url": r[5],
            "body_text": r[6],
            "content_hash": r[7],
            "version": r[8],
            "metadata_json": r[9],
            "fetched_at": r[10],
            "first_seen_at": r[11],
            "updated_at": r[12],
            "routed_at": r[13],
        }
        for r in rows
    ]


def get_authority_doc_by_hash(content_hash: str) -> dict | None:
    """Check if a document with this content hash already exists."""
    con = connect()
    cur = execute(
        con,
        "SELECT doc_id FROM authority_docs WHERE content_hash = :content_hash",
        {"content_hash": content_hash},
    )
    row = cur.fetchone()
    con.close()
    if row:
        return get_authority_doc(row[0])
    return None
