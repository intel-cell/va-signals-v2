"""Federal Register + eCFR database functions."""

from .core import connect, execute, _count_inserted_rows


def upsert_fr_seen(
    doc_id: str,
    published_date: str,
    first_seen_at: str,
    source_url: str,
    comments_close_date: str | None = None,
    effective_date: str | None = None,
    document_type: str | None = None,
    title: str | None = None,
) -> bool:
    """
    Insert or update FR document. Returns True if inserted (new), False if already existed.

    New fields (optional):
    - comments_close_date: Date when comments close (ISO format)
    - effective_date: Date when rule becomes effective (ISO format)
    - document_type: Type of document (proposed rule, final rule, notice, etc.)
    - title: Document title
    """
    con = connect()
    cur = execute(con, "SELECT doc_id FROM fr_seen WHERE doc_id = :doc_id", {"doc_id": doc_id})
    exists = cur.fetchone() is not None
    if not exists:
        execute(
            con,
            """INSERT INTO fr_seen(doc_id, published_date, first_seen_at, source_url,
                   comments_close_date, effective_date, document_type, title)
               VALUES(:doc_id, :published_date, :first_seen_at, :source_url,
                   :comments_close_date, :effective_date, :document_type, :title)""",
            {
                "doc_id": doc_id,
                "published_date": published_date,
                "first_seen_at": first_seen_at,
                "source_url": source_url,
                "comments_close_date": comments_close_date,
                "effective_date": effective_date,
                "document_type": document_type,
                "title": title,
            },
        )
        con.commit()
    con.close()
    return not exists


def update_fr_seen_dates(
    doc_id: str,
    comments_close_date: str | None = None,
    effective_date: str | None = None,
    document_type: str | None = None,
    title: str | None = None,
) -> bool:
    """
    Update FR document with date fields. Returns True if updated, False if not found.
    Only updates non-NULL values.
    """
    con = connect()
    cur = execute(con, "SELECT doc_id FROM fr_seen WHERE doc_id = :doc_id", {"doc_id": doc_id})
    exists = cur.fetchone() is not None
    if exists:
        updates = []
        params = {"doc_id": doc_id}
        if comments_close_date is not None:
            updates.append("comments_close_date = :comments_close_date")
            params["comments_close_date"] = comments_close_date
        if effective_date is not None:
            updates.append("effective_date = :effective_date")
            params["effective_date"] = effective_date
        if document_type is not None:
            updates.append("document_type = :document_type")
            params["document_type"] = document_type
        if title is not None:
            updates.append("title = :title")
            params["title"] = title

        if updates:
            execute(
                con,
                f"UPDATE fr_seen SET {', '.join(updates)} WHERE doc_id = :doc_id",
                params,
            )
            con.commit()
    con.close()
    return exists


def get_existing_fr_doc_ids(doc_ids: list[str]) -> set[str]:
    """
    Return the subset of doc_ids that already exist in fr_seen.
    Uses batched queries for efficiency.
    """
    if not doc_ids:
        return set()
    con = connect()
    existing: set[str] = set()
    # SQLite parameter limit is ~999, batch if needed
    batch_size = 900
    for i in range(0, len(doc_ids), batch_size):
        batch = doc_ids[i : i + batch_size]
        placeholders = ",".join(f":doc_id_{idx}" for idx in range(len(batch)))
        params = {f"doc_id_{idx}": value for idx, value in enumerate(batch)}
        cur = execute(
            con,
            f"SELECT doc_id FROM fr_seen WHERE doc_id IN ({placeholders})",
            params,
        )
        existing.update(row[0] for row in cur.fetchall())
    con.close()
    return existing


def bulk_insert_fr_seen(docs: list[dict]) -> int:
    """
    Insert multiple fr_seen records in a single transaction.
    Each doc should have: doc_id, published_date, first_seen_at, source_url.
    Returns count of inserted rows.
    """
    if not docs:
        return 0
    con = connect()
    inserted = _count_inserted_rows(
        con,
        """INSERT INTO fr_seen(doc_id, published_date, first_seen_at, source_url)
           VALUES(:doc_id, :published_date, :first_seen_at, :source_url)
           ON CONFLICT(doc_id) DO NOTHING""",
        docs,
    )
    con.commit()
    con.close()
    return inserted


def upsert_ecfr_seen(doc_id: str, last_modified: str, etag: str, first_seen_at: str, source_url: str) -> bool:
    """
    Returns True if inserted or changed; False if unchanged.
    Change detection is based on (last_modified, etag).
    """
    con = connect()
    cur = execute(
        con,
        "SELECT last_modified, etag FROM ecfr_seen WHERE doc_id = :doc_id",
        {"doc_id": doc_id},
    )
    row = cur.fetchone()

    if row is None:
        execute(
            con,
            """INSERT INTO ecfr_seen(doc_id, last_modified, etag, first_seen_at, source_url)
               VALUES(:doc_id, :last_modified, :etag, :first_seen_at, :source_url)""",
            {
                "doc_id": doc_id,
                "last_modified": last_modified,
                "etag": etag,
                "first_seen_at": first_seen_at,
                "source_url": source_url,
            },
        )
        con.commit()
        con.close()
        return True

    prev_last_modified, prev_etag = row[0], row[1]
    if (prev_last_modified != last_modified) or (prev_etag != etag):
        execute(
            con,
            """UPDATE ecfr_seen
               SET last_modified=:last_modified, etag=:etag, first_seen_at=:first_seen_at, source_url=:source_url
               WHERE doc_id=:doc_id""",
            {
                "doc_id": doc_id,
                "last_modified": last_modified,
                "etag": etag,
                "first_seen_at": first_seen_at,
                "source_url": source_url,
            },
        )
        con.commit()
        con.close()
        return True

    con.close()
    return False
