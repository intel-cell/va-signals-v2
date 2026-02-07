"""
Federal Register Document Details Fetcher

Fetches detailed metadata for FR documents including:
- comments_close_on (comment deadline)
- effective_on (effective date)
- type (document type: rule, proposed rule, notice, etc.)
- title

Uses the Federal Register API: https://www.federalregister.gov/developers/documentation/api/v1
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

FR_API_BASE = "https://www.federalregister.gov/api/v1"
FR_FIELDS = [
    "document_number",
    "title",
    "type",
    "comments_close_on",
    "effective_on",
    "publication_date",
]

# Thread-local session with retry/backoff
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    """Return a session with retry strategy."""
    global _session
    if _session is None:
        _session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
        _session.headers.update({"Accept": "application/json"})
    return _session


def fetch_fr_document_details(document_number: str, timeout: int = 30) -> dict[str, Any] | None:
    """
    Fetch detailed metadata for a single FR document.

    Args:
        document_number: FR document number (e.g., "2026-01234")
        timeout: Request timeout in seconds

    Returns:
        Dict with document details or None if not found/error
    """
    url = f"{FR_API_BASE}/documents/{document_number}.json"
    params = {"fields[]": FR_FIELDS}

    try:
        response = _get_session().get(url, params=params, timeout=timeout)
        if response.status_code == 404:
            logger.warning(f"FR document not found: {document_number}")
            return None
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching FR document {document_number}: {e}")
        return None


def fetch_fr_documents_by_date(
    publication_date: str,
    agencies: list[str] | None = None,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """
    Fetch all FR documents for a given publication date.

    Args:
        publication_date: ISO date string (YYYY-MM-DD)
        agencies: Optional list of agency slugs to filter (e.g., ["veterans-affairs-department"])
        timeout: Request timeout in seconds

    Returns:
        List of document details
    """
    url = f"{FR_API_BASE}/documents.json"
    params = {
        "fields[]": FR_FIELDS,
        "conditions[publication_date][is]": publication_date,
        "per_page": 1000,
    }

    if agencies:
        params["conditions[agencies][]"] = agencies

    try:
        response = _get_session().get(url, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    except requests.RequestException as e:
        logger.error(f"Error fetching FR documents for {publication_date}: {e}")
        return []


def fetch_fr_documents_batch(
    document_numbers: list[str],
    max_workers: int = 4,
    timeout: int = 30,
) -> dict[str, dict[str, Any]]:
    """
    Fetch details for multiple FR documents in parallel.

    Args:
        document_numbers: List of FR document numbers
        max_workers: Number of parallel workers
        timeout: Request timeout per document

    Returns:
        Dict mapping document_number -> document details
    """
    results: dict[str, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_doc = {
            executor.submit(fetch_fr_document_details, doc_num, timeout): doc_num
            for doc_num in document_numbers
        }

        for future in as_completed(future_to_doc):
            doc_num = future_to_doc[future]
            try:
                details = future.result()
                if details:
                    results[doc_num] = details
            except Exception as e:
                logger.error(f"Error fetching {doc_num}: {e}")

    return results


def extract_document_dates(doc_details: dict[str, Any]) -> dict[str, str | None]:
    """
    Extract date fields from FR document details.

    Returns:
        Dict with comments_close_date, effective_date, document_type, title
    """
    return {
        "comments_close_date": doc_details.get("comments_close_on"),
        "effective_date": doc_details.get("effective_on"),
        "document_type": doc_details.get("type"),
        "title": doc_details.get("title"),
    }


def enrich_fr_documents_with_dates(
    doc_ids: list[str], max_workers: int = 4
) -> dict[str, dict[str, str | None]]:
    """
    Fetch and extract date information for FR documents.

    The doc_id format from fr_bulk is "FR-YYYY-MM-DD" but we need the document_number
    which is typically in format "YYYY-NNNNN". This function handles the translation.

    Args:
        doc_ids: List of doc_ids from fr_seen table
        max_workers: Number of parallel workers

    Returns:
        Dict mapping doc_id -> {comments_close_date, effective_date, document_type, title}
    """
    # FR bulk doc_ids are like "FR-2026-01-15" (publication date packages)
    # We need to fetch documents by date, not by document number
    results: dict[str, dict[str, str | None]] = {}

    # Group doc_ids by publication date
    dates_to_fetch: set[str] = set()
    for doc_id in doc_ids:
        # Extract date from doc_id like "FR-2026-01-15"
        if doc_id.startswith("FR-") and len(doc_id) >= 13:
            pub_date = doc_id[3:13]  # "2026-01-15"
            dates_to_fetch.add(pub_date)

    # Fetch all documents for each date
    for pub_date in dates_to_fetch:
        docs = fetch_fr_documents_by_date(
            pub_date,
            agencies=["veterans-affairs-department"],
        )

        for doc in docs:
            doc_num = doc.get("document_number")
            if doc_num:
                dates = extract_document_dates(doc)
                # Map back using the publication date package format
                package_id = f"FR-{pub_date}"
                if package_id in doc_ids:
                    # Store with the original doc_id format
                    results[package_id] = dates

    return results
