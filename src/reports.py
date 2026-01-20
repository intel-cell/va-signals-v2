"""
Report generation system for VA Signals.

Generates daily, weekly, and custom range reports from source_runs,
fr_seen, and ecfr_seen tables.
"""

import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Allow running as a script (python -m src.reports) by setting package context
if __name__ == "__main__" and __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "src"

from .db import connect
from .provenance import utc_now_iso

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "outputs" / "reports"
FR_API_URL = "https://www.federalregister.gov/api/v1/documents.json"
MAX_FR_DOCS_FETCH = 1000  # upper bound per-day fetch
MAX_FR_DOCS_SHOWN = 50    # limit detailed listings to keep reports readable

# Shared HTTP session with retry/backoff for FR API calls
_http_session: requests.Session | None = None


def _get_http_session() -> requests.Session:
    global _http_session
    if _http_session is None:
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _http_session = session
    return _http_session


def _parse_iso_datetime(iso_str: str) -> datetime:
    """Parse ISO 8601 timestamp to datetime."""
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def _get_period_bounds(
    report_type: str, start_date: str | None = None, end_date: str | None = None
) -> tuple[datetime, datetime]:
    """
    Calculate the time period bounds for a report.

    Args:
        report_type: 'daily', 'weekly', or 'custom'
        start_date: ISO date string for custom reports
        end_date: ISO date string for custom reports

    Returns:
        Tuple of (start_datetime, end_datetime) in UTC
    """
    now = datetime.now(timezone.utc)

    if report_type == "daily":
        period_start = now - timedelta(hours=24)
        period_end = now
    elif report_type == "weekly":
        period_start = now - timedelta(days=7)
        period_end = now
    elif report_type == "custom":
        if not start_date or not end_date:
            raise ValueError("Custom reports require start_date and end_date")
        period_start = datetime.fromisoformat(start_date)
        period_end = datetime.fromisoformat(end_date)
        # Ensure they have timezone info
        if period_start.tzinfo is None:
            period_start = period_start.replace(tzinfo=timezone.utc)
        if period_end.tzinfo is None:
            # Set end of day for end_date
            period_end = period_end.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    else:
        raise ValueError(f"Unknown report_type: {report_type}")

    return period_start, period_end


def _fetch_runs_in_period(period_start: datetime, period_end: datetime) -> list[dict]:
    """Fetch source_runs within the given period."""
    con = connect()
    cur = con.cursor()
    cur.execute(
        """
        SELECT id, source_id, started_at, ended_at, status, records_fetched, errors_json
        FROM source_runs
        WHERE started_at >= ? AND started_at <= ?
        ORDER BY started_at DESC
        """,
        (period_start.isoformat(), period_end.isoformat()),
    )
    rows = cur.fetchall()
    con.close()

    runs = []
    for row in rows:
        run_id, source_id, started_at, ended_at, status, records_fetched, errors_json = row
        errors = json.loads(errors_json) if errors_json else []
        runs.append({
            "id": run_id,
            "source_id": source_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "status": status,
            "records_fetched": records_fetched,
            "errors": errors,
        })
    return runs


def _fetch_new_fr_docs_in_period(period_start: datetime, period_end: datetime) -> list[dict]:
    """Fetch fr_seen documents first seen within the given period."""
    con = connect()
    cur = con.cursor()
    cur.execute(
        """
        SELECT doc_id, published_date, first_seen_at, source_url
        FROM fr_seen
        WHERE first_seen_at >= ? AND first_seen_at <= ?
        ORDER BY first_seen_at DESC
        """,
        (period_start.isoformat(), period_end.isoformat()),
    )
    rows = cur.fetchall()
    con.close()

    docs = []
    for row in rows:
        doc_id, published_date, first_seen_at, source_url = row
        docs.append({
            "doc_id": doc_id,
            "published_date": published_date,
            "first_seen_at": first_seen_at,
            "source_url": source_url,
        })
    return docs


def _aggregate_run_stats(runs: list[dict]) -> dict:
    """Aggregate run statistics."""
    total_runs = len(runs)
    successful_runs = sum(1 for r in runs if r["status"] == "SUCCESS")
    error_runs = sum(1 for r in runs if r["status"] == "ERROR")
    no_data_runs = sum(1 for r in runs if r["status"] == "NO_DATA")

    # Group by source
    sources: dict[str, dict] = {}
    for run in runs:
        source_id = run["source_id"]
        if source_id not in sources:
            sources[source_id] = {
                "total_runs": 0,
                "successful_runs": 0,
                "error_runs": 0,
                "no_data_runs": 0,
                "total_records_fetched": 0,
            }
        sources[source_id]["total_runs"] += 1
        sources[source_id]["total_records_fetched"] += run["records_fetched"]
        if run["status"] == "SUCCESS":
            sources[source_id]["successful_runs"] += 1
        elif run["status"] == "ERROR":
            sources[source_id]["error_runs"] += 1
        elif run["status"] == "NO_DATA":
            sources[source_id]["no_data_runs"] += 1

    return {
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "error_runs": error_runs,
        "no_data_runs": no_data_runs,
        "sources": sources,
    }


def _parse_iso_date(date_str: str | None) -> date | None:
    """Parse YYYY-MM-DD into a date object."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _assess_urgency(entry: dict, today: date) -> tuple[bool, list[str]]:
    """Assess urgency based on comment close and effective dates."""
    reasons: list[str] = []

    close_date = _parse_iso_date(entry.get("comments_close_on"))
    if close_date:
        days_to_close = (close_date - today).days
        if 0 <= days_to_close <= 14:
            reasons.append(f"Comments close in {days_to_close} days ({close_date.isoformat()})")

    effective_date = _parse_iso_date(entry.get("effective_on"))
    if effective_date:
        days_to_effective = (effective_date - today).days
        if 0 <= days_to_effective <= 30:
            reasons.append(f"Effective in {days_to_effective} days ({effective_date.isoformat()})")

    return (len(reasons) > 0, reasons)


def _filter_va_docs(documents: list[dict]) -> list[dict]:
    """Return only documents associated with VA (case-insensitive)."""
    va_docs: list[dict] = []
    for doc in documents:
        agencies = [a.lower() for a in doc.get("agencies", [])]
        if any("veterans affairs" in a for a in agencies):
            va_docs.append(doc)
    return va_docs


def _shape_fr_document(entry: dict, today: date) -> dict:
    """Extract the fields we care about for FR documents."""
    agencies = [a.get("name", "").strip() for a in entry.get("agencies") or [] if a.get("name")]
    is_urgent, urgency_reasons = _assess_urgency(entry, today)

    return {
        "document_number": entry.get("document_number", ""),
        "title": (entry.get("title") or "").strip(),
        "type": entry.get("type", ""),
        "agencies": agencies,
        "publication_date": entry.get("publication_date", ""),
        "comments_close_on": entry.get("comments_close_on"),
        "effective_on": entry.get("effective_on"),
        "html_url": entry.get("html_url"),
        "comment_url": entry.get("comment_url"),
        "significant": entry.get("significant"),
        "abstract": (entry.get("abstract") or "").strip(),
        "urgency": {
            "is_urgent": is_urgent,
            "reasons": urgency_reasons,
        },
    }


def _fetch_fr_documents_for_date(publication_date: str, timeout: int = 20) -> tuple[list[dict], int, str | None]:
    """
    Fetch Federal Register documents for a given publication date.
    Returns (docs, total_count, error); docs may be empty on failure.
    """
    if not publication_date:
        return [], 0, "missing_publication_date"

    params = {
        "conditions[publication_date]": publication_date,
        "per_page": MAX_FR_DOCS_FETCH,
        "order": "newest",
    }
    session = _get_http_session()

    try:
        resp = session.get(FR_API_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        # Safety filter: keep only the requested publication_date
        results = [r for r in results if r.get("publication_date") == publication_date]
        total_count = len(results)
    except Exception as e:
        return [], 0, f"FR API fetch failed for {publication_date}: {e.__class__.__name__}"

    today = datetime.now(timezone.utc).date()
    shaped = [_shape_fr_document(entry, today) for entry in results]
    return shaped, total_count, None


def _format_highlights(documents: list[dict]) -> list[str]:
    """Create short highlights for human scanning."""
    if not documents:
        return []

    urgent_docs = [d for d in documents if d.get("urgency", {}).get("is_urgent")]
    candidates = urgent_docs[:3] if urgent_docs else documents[:3]
    highlights: list[str] = []

    for doc in candidates:
        agency = ", ".join(doc.get("agencies") or []) or "Agency TBD"
        deadlines: list[str] = []
        if doc.get("comments_close_on"):
            deadlines.append(f"comments close {doc['comments_close_on']}")
        if doc.get("effective_on"):
            deadlines.append(f"effective {doc['effective_on']}")
        deadline_part = "; ".join(deadlines)

        snippet = f"{doc.get('document_number', '')}: {doc.get('title', '')} ({agency})"
        if deadline_part:
            snippet += f" — {deadline_part}"
        highlights.append(snippet.strip())

    return highlights


def _build_report_highlights(enriched_docs: list[dict], max_items: int = 5) -> list[str]:
    """Create cross-document highlights, prioritizing urgent then VA-scoped docs."""
    if not enriched_docs:
        return []

    def collect(predicate):
        items = []
        for parent in enriched_docs:
            for doc in parent.get("documents", []):
                if predicate(parent, doc):
                    items.append((parent, doc))
        return items

    urgent = collect(lambda p, d: d.get("urgency", {}).get("is_urgent"))
    va_docs = collect(lambda p, d: p.get("documents_scope") == "veterans_affairs")
    all_docs = collect(lambda _p, _d: True)

    chosen = urgent or va_docs or all_docs
    highlights: list[str] = []
    today = datetime.now(timezone.utc).date()

    for parent, doc in chosen[:max_items]:
        title = doc.get("title") or "New Federal Register document"
        agency = ", ".join(doc.get("agencies") or []) or "Agency TBD"
        parts = [f"{parent.get('doc_id', '')} — {title}", f"({agency}; published {doc.get('publication_date','')})"]

        urgency = doc.get("urgency") or {}
        reasons = urgency.get("reasons") or []
        if reasons:
            parts.append(f"URGENT: {'; '.join(reasons)}")
        else:
            # Include nearest date if present to give some context
            close_date = _parse_iso_date(doc.get("comments_close_on"))
            effective_date = _parse_iso_date(doc.get("effective_on"))
            if close_date:
                days = (close_date - today).days
                parts.append(f"Comments close in {days} days ({close_date})")
            elif effective_date:
                days = (effective_date - today).days
                parts.append(f"Effective in {days} days ({effective_date})")

        highlights.append(" — ".join(parts))

    return highlights


def _enrich_new_documents(new_docs: list[dict]) -> list[dict]:
    """
    Enrich new FR documents with Federal Register metadata (titles, agencies, urgency).
    """
    enriched: list[dict] = []
    cache: dict[str, tuple[list[dict], int, str | None]] = {}
    for doc in new_docs:
        pub_date = doc.get("published_date", "")
        if pub_date not in cache:
            fr_documents_all, total_count, err = _fetch_fr_documents_for_date(pub_date)
            cache[pub_date] = (fr_documents_all, total_count, err)
        else:
            fr_documents_all, total_count, err = cache[pub_date]
        va_documents = _filter_va_docs(fr_documents_all)
        selected_docs = va_documents if va_documents else fr_documents_all
        selected_docs = selected_docs[:MAX_FR_DOCS_SHOWN]

        urgent_count = sum(1 for d in selected_docs if d.get("urgency", {}).get("is_urgent"))
        label = pub_date or doc.get("doc_id", "")
        available_count = len(fr_documents_all)
        if total_count and total_count < MAX_FR_DOCS_FETCH:
            available_count = total_count
        enriched.append({
            **doc,
            "why_flagged": f"New FR bulk package for {label} (first seen at {doc.get('first_seen_at', '')})",
            "document_count": len(selected_docs),
            "documents_shown": len(selected_docs),
            "veterans_affairs_documents": len(va_documents),
            "documents_scanned": len(fr_documents_all),
            "total_documents_available": available_count,
            "urgent_count": urgent_count,
            "documents_scope": "veterans_affairs" if va_documents else "all_documents",
            "highlights": _format_highlights(selected_docs),
            "documents": selected_docs,
            "truncated": (len(selected_docs) < len(va_documents)) if va_documents else (len(selected_docs) < len(fr_documents_all)),
            "fetch_error": err,
        })
    return enriched


def generate_report(
    report_type: str, start_date: str | None = None, end_date: str | None = None
) -> dict:
    """
    Generate a report for the specified type and period.

    Args:
        report_type: 'daily', 'weekly', or 'custom'
        start_date: ISO date string (required for custom, e.g., '2026-01-01')
        end_date: ISO date string (required for custom, e.g., '2026-01-15')

    Returns:
        Report dictionary with structure:
        {
            "report_type": "weekly",
            "generated_at": "2026-01-19T...",
            "period": {"start": "...", "end": "..."},
            "summary": {...},
            "runs": [...],
            "new_documents": [...]
        }
    """
    period_start, period_end = _get_period_bounds(report_type, start_date, end_date)

    # Fetch data
    runs = _fetch_runs_in_period(period_start, period_end)
    new_docs = _fetch_new_fr_docs_in_period(period_start, period_end)

    # Aggregate statistics
    stats = _aggregate_run_stats(runs)
    stats["new_fr_docs"] = len(new_docs)

    # Enrich new docs with FR metadata for context/urgency
    enriched_docs = _enrich_new_documents(new_docs)
    stats["new_fr_docs_with_metadata"] = sum(1 for d in enriched_docs if d.get("document_count", 0) > 0)
    stats["urgent_fr_docs"] = sum(d.get("urgent_count", 0) for d in enriched_docs)
    stats["va_fr_docs"] = sum(d.get("veterans_affairs_documents", 0) for d in enriched_docs)
    stats["fr_enrichment_errors"] = sum(1 for d in enriched_docs if d.get("fetch_error"))
    highlights = _build_report_highlights(enriched_docs)

    report = {
        "report_type": report_type,
        "generated_at": utc_now_iso(),
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "summary": stats,
        "runs": runs,
        "new_documents": new_docs,
        "new_documents_enriched": enriched_docs,
        "highlights": highlights,
    }

    return report


def export_json(report: dict, filepath: str) -> str:
    """
    Export report to JSON file.

    Args:
        report: Report dictionary from generate_report()
        filepath: Output file path (relative to outputs/reports/ or absolute)

    Returns:
        Absolute path to the created file
    """
    output_path = Path(filepath)
    if not output_path.is_absolute():
        output_path = REPORTS_DIR / filepath

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return str(output_path)


def _escape_csv_field(field: Any) -> str:
    """Escape a field for CSV output."""
    if field is None:
        return ""
    s = str(field)
    if "," in s or '"' in s or "\n" in s:
        return f'"{s.replace(chr(34), chr(34)+chr(34))}"'
    return s


def export_csv(report: dict, filepath: str) -> str:
    """
    Export report to CSV files (flattened tabular format).

    Creates two files:
    - {name}_runs.csv: Source run records
    - {name}_docs.csv: New documents found

    Args:
        report: Report dictionary from generate_report()
        filepath: Base output file path (without extension)

    Returns:
        Base path used (the actual files have _runs.csv and _docs.csv suffixes)
    """
    base_path = Path(filepath)
    if not base_path.is_absolute():
        base_path = REPORTS_DIR / filepath

    # Remove extension if provided
    if base_path.suffix:
        base_path = base_path.with_suffix("")

    base_path.parent.mkdir(parents=True, exist_ok=True)

    # Export runs CSV
    runs_path = base_path.parent / f"{base_path.name}_runs.csv"
    with open(runs_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow([
            "id", "source_id", "started_at", "ended_at", "status", "records_fetched", "errors"
        ])
        for run in report.get("runs", []):
            errors_str = "; ".join(run.get("errors", []))
            writer.writerow([
                run.get("id", ""),
                run.get("source_id", ""),
                run.get("started_at", ""),
                run.get("ended_at", ""),
                run.get("status", ""),
                run.get("records_fetched", 0),
                errors_str,
            ])

    # Export docs CSV
    docs_path = base_path.parent / f"{base_path.name}_docs.csv"
    with open(docs_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["doc_id", "published_date", "first_seen_at", "source_url"])
        for doc in report.get("new_documents", []):
            writer.writerow([
                doc.get("doc_id", ""),
                doc.get("published_date", ""),
                doc.get("first_seen_at", ""),
                doc.get("source_url", ""),
            ])

    # Export detailed docs CSV (with FR metadata/urgency) if available
    enriched_docs = report.get("new_documents_enriched") or []
    if enriched_docs:
        detailed_path = base_path.parent / f"{base_path.name}_docs_detailed.csv"
        with open(detailed_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            writer.writerow([
                "doc_id",
                "published_date",
                "first_seen_at",
                "document_number",
                "title",
                "type",
                "agencies",
                "comments_close_on",
                "effective_on",
                "is_urgent",
                "urgency_reasons",
                "html_url",
                "source_url",
            ])
            for parent in enriched_docs:
                for fr_doc in parent.get("documents", []) or []:
                    urgency = fr_doc.get("urgency") or {}
                    writer.writerow([
                        parent.get("doc_id", ""),
                        parent.get("published_date", ""),
                        parent.get("first_seen_at", ""),
                        fr_doc.get("document_number", ""),
                        fr_doc.get("title", ""),
                        fr_doc.get("type", ""),
                        "; ".join(fr_doc.get("agencies", [])),
                        fr_doc.get("comments_close_on") or "",
                        fr_doc.get("effective_on") or "",
                        urgency.get("is_urgent", False),
                        "; ".join(urgency.get("reasons", [])),
                        fr_doc.get("html_url") or "",
                        parent.get("source_url", ""),
                    ])

    return str(base_path)


def _generate_filename(report_type: str) -> str:
    """Generate a filename based on report type and timestamp."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{report_type}_{timestamp}"


def main():
    """CLI entry point for report generation."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.reports <type> [start_date] [end_date]")
        print("")
        print("Report types:")
        print("  daily   - Runs from last 24 hours")
        print("  weekly  - Runs from last 7 days")
        print("  custom  - Custom date range (requires start_date and end_date)")
        print("")
        print("Examples:")
        print("  python -m src.reports daily")
        print("  python -m src.reports weekly")
        print("  python -m src.reports custom 2026-01-01 2026-01-15")
        sys.exit(1)

    report_type = sys.argv[1].lower()

    if report_type not in ("daily", "weekly", "custom"):
        print(f"ERROR: Unknown report type '{report_type}'")
        print("Valid types: daily, weekly, custom")
        sys.exit(1)

    start_date = None
    end_date = None

    if report_type == "custom":
        if len(sys.argv) < 4:
            print("ERROR: Custom reports require start_date and end_date")
            print("Usage: python -m src.reports custom 2026-01-01 2026-01-15")
            sys.exit(1)
        start_date = sys.argv[2]
        end_date = sys.argv[3]

    # Generate report
    print(f"Generating {report_type} report...")
    report = generate_report(report_type, start_date, end_date)

    # Generate output filename
    filename = _generate_filename(report_type)

    # Export to JSON
    json_path = export_json(report, f"{filename}.json")
    print(f"JSON report: {json_path}")

    # Export to CSV
    csv_base = export_csv(report, filename)
    print(f"CSV reports: {csv_base}_runs.csv, {csv_base}_docs.csv")

    # Print summary
    print("")
    print("=== Report Summary ===")
    print(f"Report Type: {report['report_type']}")
    print(f"Period: {report['period']['start']} to {report['period']['end']}")
    print(f"Total Runs: {report['summary']['total_runs']}")
    print(f"  Successful: {report['summary']['successful_runs']}")
    print(f"  Errors: {report['summary']['error_runs']}")
    print(f"  No Data: {report['summary']['no_data_runs']}")
    print(f"New FR Docs: {report['summary']['new_fr_docs']}")

    if report["summary"]["sources"]:
        print("")
        print("By Source:")
        for source_id, stats in report["summary"]["sources"].items():
            print(f"  {source_id}:")
            print(f"    Runs: {stats['total_runs']} (ok={stats['successful_runs']}, err={stats['error_runs']}, no_data={stats['no_data_runs']})")
            print(f"    Records: {stats['total_records_fetched']}")


if __name__ == "__main__":
    main()
