"""
LLM-powered summarization for VA Signals Federal Register documents.

Uses Claude API (claude-sonnet) to generate veteran-focused summaries
of Federal Register rules and notices.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

# Allow running as a script (python -m src.summarize) by setting package context
if __name__ == "__main__" and __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "src"

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
from src.llm_config import SONNET_MODEL as CLAUDE_MODEL

from .db import connect, execute
from .provenance import utc_now_iso
from .secrets import get_env_or_keychain

CLAUDE_MAX_TOKENS = 1024
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"

# Rate limiting: delay between API calls (seconds)
RATE_LIMIT_DELAY = 0.5

# Federal Register API base URL
FR_API_BASE = "https://www.federalregister.gov/api/v1/documents"

# Predefined tags for categorization
VALID_TAGS = frozenset(
    [
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
    ]
)

# System prompt for veteran-focused summarization
SYSTEM_PROMPT = """You are an expert analyst specializing in veterans affairs policy and federal regulations. Your role is to summarize Federal Register documents in a way that is clear, accurate, and focused on impact to veterans and their families.

Guidelines:
1. Focus on how the document affects veterans, their families, and caregivers
2. Identify specific changes to benefits, healthcare services, claims processes, or eligibility
3. Note any deadlines, effective dates, or comment periods
4. Be factual and precise - do not speculate or editorialize
5. Use plain language accessible to a general audience

CRITICAL: Respond with ONLY valid JSON. No markdown, no explanation, no code blocks. Just the raw JSON object.

Required JSON format:
{"summary": "A brief 2-3 sentence summary", "bullet_points": ["Point 1", "Point 2", "Point 3"], "veteran_impact": "How this affects veterans", "tags": ["tag1", "tag2"]}

Valid tags: benefits, healthcare, disability, claims, appeals, housing, education, employment, mental-health, caregivers, women-veterans, rural-veterans

Only include tags directly relevant to the document."""


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------


def is_configured() -> bool:
    """Check if Anthropic API key is configured."""
    return bool(get_env_or_keychain("ANTHROPIC_API_KEY", "claude-api", allow_missing=True))


def _get_anthropic_key() -> str | None:
    """Get Anthropic API key from environment or Keychain."""
    return get_env_or_keychain("ANTHROPIC_API_KEY", "claude-api", allow_missing=True)


def fetch_document_content(doc_id: str, timeout: int = 30) -> dict[str, Any] | None:
    """
    Fetch document content. First tries to get source_url from database,
    then fetches and parses the XML.

    Args:
        doc_id: Document ID (e.g., "FR-2026-01-20.xml")
        timeout: Request timeout in seconds

    Returns:
        Dict with doc_id, title, abstract, etc. or None on error
    """
    try:
        # Get source_url from database
        con = connect()
        cur = execute(
            con,
            "SELECT source_url, published_date FROM fr_seen WHERE doc_id = :doc_id",
            {"doc_id": doc_id},
        )
        row = cur.fetchone()
        con.close()

        if not row:
            return None

        source_url, published_date = row[0], row[1]

        # Fetch the XML content
        r = requests.get(source_url, timeout=timeout)
        if r.status_code != 200:
            return None

        # Parse XML to extract key information
        from lxml import etree

        root = etree.fromstring(r.content)

        # Extract document titles and agencies from the FR XML
        titles = []
        agencies = set()

        # FR bulk XML structure: look for RULE, NOTICE, PRORULE elements
        for doc_type in ["RULE", "NOTICE", "PRORULE", "PRESDOC"]:
            for doc in root.findall(f".//{doc_type}"):
                # Get subject/title
                subject = doc.find(".//SUBJECT")
                if subject is not None and subject.text:
                    titles.append(subject.text.strip())
                # Get agency
                agency = doc.find(".//AGENCY")
                if agency is not None and agency.text:
                    agencies.add(agency.text.strip())

        # Build a summary of the day's FR content
        title = f"Federal Register - {published_date or doc_id}"
        abstract = ""
        if titles:
            # Take first 10 titles as abstract
            abstract = "Documents include: " + "; ".join(titles[:10])
            if len(titles) > 10:
                abstract += f" (and {len(titles) - 10} more)"

        return {
            "doc_id": doc_id,
            "title": title,
            "abstract": abstract,
            "publication_date": published_date,
            "agencies": list(agencies),
            "document_count": len(titles),
        }
    except Exception as e:
        print(f"Error fetching {doc_id}: {e}")
        return None


def _fetch_full_text(raw_text_url: str, timeout: int = 60) -> str | None:
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


def _save_summary(summary_record: dict[str, Any]) -> None:
    """Save summary to database."""
    con = connect()
    execute(
        con,
        """INSERT INTO fr_summaries
           (doc_id, summary, bullet_points, veteran_impact, tags, summarized_at)
           VALUES (:doc_id, :summary, :bullet_points, :veteran_impact, :tags, :summarized_at)
           ON CONFLICT(doc_id) DO UPDATE SET
             summary = excluded.summary,
             bullet_points = excluded.bullet_points,
             veteran_impact = excluded.veteran_impact,
             tags = excluded.tags,
             summarized_at = excluded.summarized_at""",
        {
            "doc_id": summary_record["doc_id"],
            "summary": summary_record["summary"],
            "bullet_points": json.dumps(summary_record["bullet_points"]),
            "veteran_impact": summary_record["veteran_impact"],
            "tags": json.dumps(summary_record["tags"]),
            "summarized_at": summary_record["summarized_at"],
        },
    )
    con.commit()
    con.close()


def get_summary(doc_id: str) -> dict[str, Any] | None:
    """
    Retrieve a saved summary from database.

    Args:
        doc_id: Federal Register document ID

    Returns:
        Summary record or None if not found
    """
    _init_summaries_table()
    con = connect()
    cur = execute(
        con,
        "SELECT doc_id, summary, bullet_points, veteran_impact, tags, summarized_at FROM fr_summaries WHERE doc_id = :doc_id",
        {"doc_id": doc_id},
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


def get_unsummarized_doc_ids(limit: int = 100) -> list[str]:
    """
    Get doc_ids from fr_seen that don't have summaries yet.

    Args:
        limit: Maximum number of doc_ids to return

    Returns:
        List of doc_ids needing summarization
    """
    _init_summaries_table()
    con = connect()
    cur = execute(
        con,
        """SELECT f.doc_id FROM fr_seen f
           LEFT JOIN fr_summaries s ON f.doc_id = s.doc_id
           WHERE s.doc_id IS NULL
           ORDER BY f.first_seen_at DESC
           LIMIT :limit""",
        {"limit": limit},
    )
    doc_ids = [row[0] for row in cur.fetchall()]
    con.close()
    return doc_ids


# -----------------------------------------------------------------------------
# LLM Summarization
# -----------------------------------------------------------------------------


def _extract_json(text: str) -> dict[str, Any] | None:
    """
    Extract JSON from text, handling cases where Claude adds extra text.
    """
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    import re

    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return None


def _call_claude(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    timeout: int = 60,
    retries: int = 2,
) -> dict[str, Any] | None:
    """
    Make a message request to Claude API with retry logic.

    Args:
        system_prompt: System message content
        user_prompt: User message content
        api_key: Anthropic API key
        timeout: Request timeout in seconds
        retries: Number of retries on failure

    Returns:
        Parsed JSON response or None on error
    """
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": CLAUDE_MAX_TOKENS,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
    }

    for attempt in range(retries + 1):
        try:
            r = requests.post(CLAUDE_API_URL, headers=headers, json=payload, timeout=timeout)
            r.raise_for_status()

            data = r.json()
            content = data.get("content", [{}])[0].get("text", "")

            if not content:
                continue

            result = _extract_json(content)
            if result:
                return result

            # If JSON extraction failed, retry with explicit reminder
            if attempt < retries:
                payload["messages"] = [
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": "Please respond with ONLY valid JSON, no other text.",
                    },
                ]
                time.sleep(0.5)

        except requests.exceptions.RequestException as e:
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"Claude API request error: {e}")
            return None
        except Exception as e:
            print(f"Claude API error: {e}")
            return None

    return None


def _build_user_prompt(title: str, abstract: str, full_text: str | None = None) -> str:
    """Build the user prompt for summarization."""
    parts = [f"Title: {title}"]

    if abstract:
        parts.append(f"\nAbstract: {abstract}")

    if full_text:
        # Truncate to reasonable length for token limits
        truncated = full_text[:30000]
        parts.append(f"\nFull Text:\n{truncated}")

    return "\n".join(parts)


def _validate_tags(tags: list[str]) -> list[str]:
    """Filter tags to only include valid predefined tags."""
    return [t.lower() for t in tags if t.lower() in VALID_TAGS]


def summarize_document(
    doc_id: str,
    title: str,
    abstract: str,
    full_text: str | None = None,
) -> dict[str, Any] | None:
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
    api_key = _get_anthropic_key()
    if not api_key:
        return None

    if not title and not abstract and not full_text:
        return None

    user_prompt = _build_user_prompt(title, abstract, full_text)
    result = _call_claude(SYSTEM_PROMPT, user_prompt, api_key)

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
    full_text: str | None = None,
) -> dict[str, Any] | None:
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
    docs: list[dict[str, Any]],
    fetch_content: bool = True,
    store: bool = True,
) -> list[dict[str, Any]]:
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
    results: list[dict[str, Any]] = []

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
            print(f"[{i + 1}/{len(docs)}] Summarized: {doc_id}")
        else:
            print(f"[{i + 1}/{len(docs)}] Failed: {doc_id}")

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
        print("ERROR: ANTHROPIC_API_KEY not configured")
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
        print("ERROR: ANTHROPIC_API_KEY not configured")
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
        help="Check if Claude API is configured",
    )

    args = parser.parse_args()

    if args.check:
        if is_configured():
            print("Claude API configured: Yes")
        else:
            print("Claude API configured: No (ANTHROPIC_API_KEY not set)")
        return

    if args.pending:
        _cli_summarize_pending(limit=args.limit)
    elif args.doc_id:
        _cli_summarize_one(args.doc_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
