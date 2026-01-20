"""
LLM-powered summarization for VA Signals Federal Register documents.

Uses OpenAI API (gpt-4o-mini) to generate veteran-focused summaries
of Federal Register rules and notices.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# Allow running as a script (python -m src.summarize) by setting package context
if __name__ == "__main__" and __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "src"

from .provenance import utc_now_iso
from .db import connect

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

OPENAI_MODEL = "gpt-4o-mini"
OPENAI_TEMPERATURE = 0.3
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# Rate limiting: delay between API calls (seconds)
RATE_LIMIT_DELAY = 0.5

# Federal Register API base URL
FR_API_BASE = "https://www.federalregister.gov/api/v1/documents"

# Predefined tags for categorization
VALID_TAGS = frozenset([
    "benefits",
    "healthcare",
    "disability",
    "claims",
    "appeals",
    "housing",
    "education",
    "employment",
    "mental-health",
    "caregivers",
    "women-veterans",
    "rural-veterans",
])

# System prompt for veteran-focused summarization
SYSTEM_PROMPT = """You are an expert analyst specializing in veterans affairs policy and federal regulations. Your role is to summarize Federal Register documents in a way that is clear, accurate, and focused on impact to veterans and their families.

Guidelines:
1. Focus on how the document affects veterans, their families, and caregivers
2. Identify specific changes to benefits, healthcare services, claims processes, or eligibility
3. Note any deadlines, effective dates, or comment periods
4. Be factual and precise - do not speculate or editorialize
5. Use plain language accessible to a general audience

You must respond with valid JSON in this exact format:
{
  "summary": "A brief 2-3 sentence summary of the document",
  "bullet_points": ["Key point 1", "Key point 2", "Key point 3"],
  "veteran_impact": "A concise explanation of how this affects veterans",
  "tags": ["tag1", "tag2"]
}

For tags, select only from this list: benefits, healthcare, disability, claims, appeals, housing, education, employment, mental-health, caregivers, women-veterans, rural-veterans

Only include tags that are directly relevant to the document content."""


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------


def is_configured() -> bool:
    """Check if OpenAI API key is configured."""
    return bool(os.environ.get("OPENAI_API_KEY"))


def _get_openai_key() -> Optional[str]:
    """Get OpenAI API key from environment."""
    return os.environ.get("OPENAI_API_KEY")


def fetch_document_content(doc_id: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
    """
    Fetch document content from Federal Register API.

    Args:
        doc_id: Federal Register document ID (e.g., "2026-00123")
        timeout: Request timeout in seconds

    Returns:
        Dict with title, abstract, full_text_xml_url, html_url, etc. or None on error
    """
    try:
        # FR API accepts document numbers directly
        url = f"{FR_API_BASE}/{doc_id}.json"
        r = requests.get(url, timeout=timeout)

        if r.status_code == 404:
            return None
        r.raise_for_status()

        data = r.json()
        return {
            "doc_id": doc_id,
            "title": data.get("title", ""),
            "abstract": data.get("abstract", ""),
            "document_number": data.get("document_number", ""),
            "type": data.get("type", ""),
            "publication_date": data.get("publication_date", ""),
            "effective_on": data.get("effective_on"),
            "html_url": data.get("html_url", ""),
            "raw_text_url": data.get("raw_text_url", ""),
            "agencies": [a.get("name", "") for a in data.get("agencies", [])],
        }
    except Exception:
        return None


def _fetch_full_text(raw_text_url: str, timeout: int = 60) -> Optional[str]:
    """
    Fetch full text content from Federal Register.

    Args:
        raw_text_url: URL to raw text version of document
        timeout: Request timeout in seconds

    Returns:
        Full text content or None on error
    """
    if not raw_text_url:
        return None
    try:
        r = requests.get(raw_text_url, timeout=timeout)
        r.raise_for_status()
        # Limit text length to avoid token limits
        text = r.text[:50000]
        return text
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Database operations
# -----------------------------------------------------------------------------


def _init_summaries_table() -> None:
    """Create fr_summaries table if it doesn't exist."""
    con = connect()
    con.execute("""
        CREATE TABLE IF NOT EXISTS fr_summaries (
            doc_id TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            bullet_points TEXT NOT NULL,
            veteran_impact TEXT NOT NULL,
            tags TEXT NOT NULL,
            summarized_at TEXT NOT NULL,
            FOREIGN KEY (doc_id) REFERENCES fr_seen(doc_id)
        )
    """)
    con.commit()
    con.close()


def _save_summary(summary_record: Dict[str, Any]) -> None:
    """Save summary to database."""
    con = connect()
    con.execute(
        """INSERT OR REPLACE INTO fr_summaries
           (doc_id, summary, bullet_points, veteran_impact, tags, summarized_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            summary_record["doc_id"],
            summary_record["summary"],
            json.dumps(summary_record["bullet_points"]),
            summary_record["veteran_impact"],
            json.dumps(summary_record["tags"]),
            summary_record["summarized_at"],
        ),
    )
    con.commit()
    con.close()


def get_summary(doc_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a saved summary from database.

    Args:
        doc_id: Federal Register document ID

    Returns:
        Summary record or None if not found
    """
    _init_summaries_table()
    con = connect()
    cur = con.cursor()
    cur.execute(
        "SELECT doc_id, summary, bullet_points, veteran_impact, tags, summarized_at FROM fr_summaries WHERE doc_id = ?",
        (doc_id,),
    )
    row = cur.fetchone()
    con.close()

    if row is None:
        return None

    return {
        "doc_id": row[0],
        "summary": row[1],
        "bullet_points": json.loads(row[2]),
        "veteran_impact": row[3],
        "tags": json.loads(row[4]),
        "summarized_at": row[5],
    }


def get_unsummarized_doc_ids(limit: int = 100) -> List[str]:
    """
    Get doc_ids from fr_seen that don't have summaries yet.

    Args:
        limit: Maximum number of doc_ids to return

    Returns:
        List of doc_ids needing summarization
    """
    _init_summaries_table()
    con = connect()
    cur = con.cursor()
    cur.execute(
        """SELECT f.doc_id FROM fr_seen f
           LEFT JOIN fr_summaries s ON f.doc_id = s.doc_id
           WHERE s.doc_id IS NULL
           ORDER BY f.first_seen_at DESC
           LIMIT ?""",
        (limit,),
    )
    doc_ids = [row[0] for row in cur.fetchall()]
    con.close()
    return doc_ids


# -----------------------------------------------------------------------------
# LLM Summarization
# -----------------------------------------------------------------------------


def _call_openai(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    timeout: int = 60,
) -> Optional[Dict[str, Any]]:
    """
    Make a chat completion request to OpenAI API.

    Args:
        system_prompt: System message content
        user_prompt: User message content
        api_key: OpenAI API key
        timeout: Request timeout in seconds

    Returns:
        Parsed JSON response or None on error
    """
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": OPENAI_TEMPERATURE,
            "response_format": {"type": "json_object"},
        }

        r = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()

        data = r.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not content:
            return None

        return json.loads(content)
    except Exception:
        return None


def _build_user_prompt(title: str, abstract: str, full_text: Optional[str] = None) -> str:
    """Build the user prompt for summarization."""
    parts = [f"Title: {title}"]

    if abstract:
        parts.append(f"\nAbstract: {abstract}")

    if full_text:
        # Truncate to reasonable length for token limits
        truncated = full_text[:30000]
        parts.append(f"\nFull Text:\n{truncated}")

    return "\n".join(parts)


def _validate_tags(tags: List[str]) -> List[str]:
    """Filter tags to only include valid predefined tags."""
    return [t.lower() for t in tags if t.lower() in VALID_TAGS]


def summarize_document(
    doc_id: str,
    title: str,
    abstract: str,
    full_text: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Generate a veteran-focused summary of a Federal Register document.

    Args:
        doc_id: Federal Register document ID (e.g., "2026-00123")
        title: Document title
        abstract: Document abstract/summary
        full_text: Optional full text content

    Returns:
        Summary record dict or None on error:
        {
            "doc_id": "2026-00123",
            "summary": "Brief 2-3 sentence summary",
            "bullet_points": ["Key point 1", "Key point 2", "Key point 3"],
            "veteran_impact": "How this affects veterans",
            "tags": ["benefits", "healthcare", ...],
            "summarized_at": "2026-01-19T..."
        }
    """
    api_key = _get_openai_key()
    if not api_key:
        return None

    if not title and not abstract and not full_text:
        return None

    user_prompt = _build_user_prompt(title, abstract, full_text)
    result = _call_openai(SYSTEM_PROMPT, user_prompt, api_key)

    if result is None:
        return None

    # Validate and structure response
    summary_record = {
        "doc_id": doc_id,
        "summary": result.get("summary", ""),
        "bullet_points": result.get("bullet_points", []),
        "veteran_impact": result.get("veteran_impact", ""),
        "tags": _validate_tags(result.get("tags", [])),
        "summarized_at": utc_now_iso(),
    }

    # Basic validation
    if not summary_record["summary"]:
        return None

    return summary_record


def summarize_and_store(
    doc_id: str,
    title: str,
    abstract: str,
    full_text: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Summarize a document and store the result in the database.

    Args:
        doc_id: Federal Register document ID
        title: Document title
        abstract: Document abstract
        full_text: Optional full text content

    Returns:
        Summary record or None on error
    """
    _init_summaries_table()

    summary_record = summarize_document(doc_id, title, abstract, full_text)
    if summary_record is None:
        return None

    _save_summary(summary_record)
    return summary_record


def summarize_batch(
    docs: List[Dict[str, Any]],
    fetch_content: bool = True,
    store: bool = True,
) -> List[Dict[str, Any]]:
    """
    Summarize multiple documents with rate limiting.

    Args:
        docs: List of dicts with doc_id, title, abstract (and optionally full_text)
        fetch_content: If True, fetch content from FR API for docs without title/abstract
        store: If True, store summaries in database

    Returns:
        List of successfully generated summary records
    """
    if not is_configured():
        return []

    _init_summaries_table()
    results: List[Dict[str, Any]] = []

    for i, doc in enumerate(docs):
        doc_id = doc.get("doc_id", "")
        title = doc.get("title", "")
        abstract = doc.get("abstract", "")
        full_text = doc.get("full_text")

        # Fetch content if needed
        if fetch_content and not title and not abstract:
            fetched = fetch_document_content(doc_id)
            if fetched:
                title = fetched.get("title", "")
                abstract = fetched.get("abstract", "")
                # Optionally fetch full text
                raw_url = fetched.get("raw_text_url")
                if raw_url and not full_text:
                    full_text = _fetch_full_text(raw_url)

        # Generate summary
        if store:
            summary = summarize_and_store(doc_id, title, abstract, full_text)
        else:
            summary = summarize_document(doc_id, title, abstract, full_text)

        if summary:
            results.append(summary)
            print(f"[{i+1}/{len(docs)}] Summarized: {doc_id}")
        else:
            print(f"[{i+1}/{len(docs)}] Failed: {doc_id}")

        # Rate limiting delay (skip on last item)
        if i < len(docs) - 1:
            time.sleep(RATE_LIMIT_DELAY)

    return results


# -----------------------------------------------------------------------------
# CLI Interface
# -----------------------------------------------------------------------------


def _cli_summarize_one(doc_id: str) -> None:
    """Summarize a single document by ID."""
    if not is_configured():
        print("ERROR: OPENAI_API_KEY not configured")
        sys.exit(1)

    # Check if already summarized
    existing = get_summary(doc_id)
    if existing:
        print(f"Document {doc_id} already summarized:")
        print(json.dumps(existing, indent=2))
        return

    # Fetch content
    print(f"Fetching content for {doc_id}...")
    content = fetch_document_content(doc_id)
    if not content:
        print(f"ERROR: Could not fetch document {doc_id}")
        sys.exit(1)

    title = content.get("title", "")
    abstract = content.get("abstract", "")

    # Optionally fetch full text
    full_text = None
    raw_url = content.get("raw_text_url")
    if raw_url:
        print("Fetching full text...")
        full_text = _fetch_full_text(raw_url)

    # Generate summary
    print("Generating summary...")
    summary = summarize_and_store(doc_id, title, abstract, full_text)

    if summary:
        print("\nSummary generated:")
        print(json.dumps(summary, indent=2))
    else:
        print("ERROR: Failed to generate summary")
        sys.exit(1)


def _cli_summarize_pending(limit: int = 10) -> None:
    """Summarize all unsummarized documents."""
    if not is_configured():
        print("ERROR: OPENAI_API_KEY not configured")
        sys.exit(1)

    doc_ids = get_unsummarized_doc_ids(limit=limit)
    if not doc_ids:
        print("No unsummarized documents found.")
        return

    print(f"Found {len(doc_ids)} unsummarized documents")

    docs = [{"doc_id": did} for did in doc_ids]
    results = summarize_batch(docs, fetch_content=True, store=True)

    print(f"\nCompleted: {len(results)}/{len(doc_ids)} documents summarized")


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Summarize Federal Register documents for VA Signals"
    )
    parser.add_argument(
        "doc_id",
        nargs="?",
        help="Document ID to summarize (e.g., 2026-00123)",
    )
    parser.add_argument(
        "--pending",
        action="store_true",
        help="Summarize all unsummarized documents",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum documents to process with --pending (default: 10)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if OpenAI API is configured",
    )

    args = parser.parse_args()

    if args.check:
        if is_configured():
            print("OpenAI API configured: Yes")
        else:
            print("OpenAI API configured: No (OPENAI_API_KEY not set)")
        return

    if args.pending:
        _cli_summarize_pending(limit=args.limit)
    elif args.doc_id:
        _cli_summarize_one(args.doc_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
