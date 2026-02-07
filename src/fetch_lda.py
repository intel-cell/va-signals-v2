"""
Fetch VA-related lobbying disclosure filings from LDA.gov API.

LDA.gov API v1: https://lda.gov/api/v1/
- Anonymous access, 15 req/min rate limit
- VA = government entity ID 42
- VET = lobbying issue code for Veterans affairs

Usage:
    python -m src.fetch_lda [--mode daily|quarterly] [--since YYYY-MM-DD] [--dry-run]
"""

import json
import logging
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

import certifi

from .resilience.circuit_breaker import lda_gov_cb
from .resilience.retry import retry_api_call
from .resilience.wiring import circuit_breaker_sync, with_timeout

logger = logging.getLogger(__name__)

LDA_BASE_URL = "https://lda.gov/api/v1"
VA_ENTITY_ID = 42
VET_ISSUE_CODE = "VET"

# Rate limiting: 15 req/min = 1 req per 4 seconds
_MIN_REQUEST_INTERVAL = 4.0
_last_request_time = 0.0

# Filing types
REGISTRATION_TYPES = ["RR"]
QUARTERLY_TYPES = ["Q1", "Q2", "Q3", "Q4"]
AMENDMENT_TYPES = ["RA", "1A", "2A", "3A", "4A"]
MONTHLY_TYPES = ["MM", "MT", "MA"]

# VA keywords for relevance scoring
VA_KEYWORDS = [
    "veterans affairs",
    "department of veterans affairs",
    "va ",
    "vba",
    "vha",
    "nca",
    "veterans benefits",
    "veterans health",
    "title 38",
    "gi bill",
    "pact act",
    "veteran",
    "service-connected",
]

VA_COVERED_POSITION_KEYWORDS = [
    "veterans affairs",
    "va ",
    "vba",
    "vha",
    "veterans benefits administration",
    "veterans health administration",
    "national cemetery administration",
]


def _rate_limit():
    """Enforce rate limiting between requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


@retry_api_call
@with_timeout(45, name="lda_gov")
@circuit_breaker_sync(lda_gov_cb)
def _fetch_json(url: str, params: dict | None = None) -> dict:
    """
    Fetch JSON from LDA.gov API with rate limiting and pagination support.

    Args:
        url: Full URL or path (will be prepended with LDA_BASE_URL if relative)
        params: Query parameters dict

    Returns:
        Parsed JSON response dict
    """
    if not url.startswith("http"):
        url = f"{LDA_BASE_URL}/{url.lstrip('/')}"

    if params:
        query_string = urllib.parse.urlencode(params, doseq=True)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{query_string}"

    _rate_limit()

    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "VA-Signals/2.0 (veterans-policy-monitor)",
        },
    )
    context = ssl.create_default_context(cafile=certifi.where())

    try:
        with urllib.request.urlopen(req, timeout=30, context=context) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            logger.warning("LDA.gov rate limited (429), waiting 60s...")
            time.sleep(60)
            return _fetch_json(url)  # Retry once
        raise


def _fetch_all_pages(url: str, params: dict, max_results: int = 500) -> list[dict]:
    """
    Fetch all pages from a paginated LDA.gov endpoint.

    Args:
        url: API endpoint path
        params: Query parameters
        max_results: Stop after this many results

    Returns:
        List of result dicts
    """
    results = []
    page_url = None

    while len(results) < max_results:
        if page_url:
            data = _fetch_json(page_url)
        else:
            data = _fetch_json(url, params)

        batch = data.get("results", [])
        if not batch:
            break

        results.extend(batch)

        # Check for next page
        next_url = data.get("next")
        if not next_url:
            break
        page_url = next_url

    return results[:max_results]


def fetch_filings_since(
    since_date: str,
    filing_types: list[str] | None = None,
    govt_entity_id: int = VA_ENTITY_ID,
    max_results: int = 500,
) -> list[dict]:
    """
    Fetch filings posted since a given date targeting a government entity.

    Args:
        since_date: ISO date string (YYYY-MM-DD)
        filing_types: Filter by filing types (e.g., ["RR", "Q1"])
        govt_entity_id: Government entity ID (default: 42 = VA)
        max_results: Maximum filings to return

    Returns:
        List of normalized filing dicts
    """
    params = {
        "filing_dt_posted_after": since_date,
        "govt_entities": str(govt_entity_id),
    }

    if filing_types:
        params["filing_type"] = filing_types

    raw_filings = _fetch_all_pages("filings/", params, max_results=max_results)
    logger.info(f"LDA: Fetched {len(raw_filings)} filings since {since_date}")

    return [_normalize_filing(f) for f in raw_filings]


def fetch_registrations_since(since_date: str, max_results: int = 100) -> list[dict]:
    """Fetch new lobbyist registrations targeting VA since a date."""
    return fetch_filings_since(
        since_date=since_date,
        filing_types=REGISTRATION_TYPES,
        max_results=max_results,
    )


def fetch_amendments_since(since_date: str, max_results: int = 200) -> list[dict]:
    """Fetch amendments to existing lobbying campaigns targeting VA since a date."""
    return fetch_filings_since(
        since_date=since_date,
        filing_types=AMENDMENT_TYPES,
        max_results=max_results,
    )


def _normalize_filing(raw: dict) -> dict:
    """
    Normalize a raw LDA.gov filing response into our schema.

    Args:
        raw: Raw filing dict from LDA.gov API

    Returns:
        Normalized filing dict matching lda_filings schema
    """
    filing_uuid = raw.get("filing_uuid", "")

    # Extract registrant
    registrant = raw.get("registrant", {}) or {}
    registrant_name = registrant.get("name", "Unknown")
    registrant_id = str(registrant.get("id", "")) if registrant.get("id") else None

    # Extract client
    client = raw.get("client", {}) or {}
    client_name = client.get("name", "Unknown")
    client_id = str(client.get("id", "")) if client.get("id") else None

    # Extract lobbying activities
    lobbying_activities = raw.get("lobbying_activities", []) or []
    issue_codes = []
    specific_issues = []
    govt_entities = []

    for activity in lobbying_activities:
        issue_code = activity.get("general_issue_code")
        if issue_code:
            issue_codes.append(issue_code)

        specific = activity.get("description", "")
        if specific:
            specific_issues.append(specific)

        for entity in activity.get("government_entities", []) or []:
            entity_name = entity.get("name", "")
            if entity_name:
                govt_entities.append(entity_name)

    # Extract lobbyists with covered positions
    lobbyists = []
    covered_positions = []
    for activity in lobbying_activities:
        for lob in activity.get("lobbyists", []) or []:
            lobbyist_info = {
                "name": f"{lob.get('first_name', '')} {lob.get('last_name', '')}".strip(),
                "covered_position": lob.get("covered_official_position", ""),
            }
            lobbyists.append(lobbyist_info)
            if lobbyist_info["covered_position"]:
                covered_positions.append(lobbyist_info)

    # Foreign entity detection
    foreign_entities = raw.get("foreign_entities", []) or []
    foreign_entity_listed = 1 if foreign_entities else 0

    # Build source URL
    source_url = f"https://lda.gov/filings/{filing_uuid}/"

    # Determine filing type/period
    filing_type = raw.get("filing_type", "")
    filing_year = raw.get("filing_year")
    filing_period = raw.get("filing_period", "")

    # Determine when posted
    dt_posted = raw.get("dt_posted", "") or raw.get("filing_date", "")

    now_iso = datetime.now(UTC).isoformat()

    filing = {
        "filing_uuid": filing_uuid,
        "filing_type": filing_type,
        "filing_year": filing_year,
        "filing_period": filing_period,
        "dt_posted": dt_posted,
        "registrant_name": registrant_name,
        "registrant_id": registrant_id,
        "client_name": client_name,
        "client_id": client_id,
        "income_amount": raw.get("income"),
        "expense_amount": raw.get("expenses"),
        "lobbying_issues_json": json.dumps(list(set(issue_codes))) if issue_codes else None,
        "specific_issues_text": "\n---\n".join(specific_issues) if specific_issues else None,
        "govt_entities_json": json.dumps(list(set(govt_entities))) if govt_entities else None,
        "lobbyists_json": json.dumps(lobbyists) if lobbyists else None,
        "foreign_entity_listed": foreign_entity_listed,
        "foreign_entities_json": json.dumps(foreign_entities) if foreign_entities else None,
        "covered_positions_json": json.dumps(covered_positions) if covered_positions else None,
        "source_url": source_url,
        "first_seen_at": now_iso,
        "updated_at": None,
    }

    # Compute VA relevance
    score, reason = _compute_va_relevance(filing, govt_entities, covered_positions)
    filing["va_relevance_score"] = score
    filing["va_relevance_reason"] = reason

    return filing


def _compute_va_relevance(
    filing: dict,
    govt_entities: list[str],
    covered_positions: list[dict],
) -> tuple[str, str]:
    """
    Compute deterministic VA relevance score for a filing.

    Scoring tiers:
        CRITICAL: Foreign entity + VA targeting, covered position at VA
        HIGH: Entity 42 targeted directly, new registration targeting VA
        MEDIUM: VET issue code, VA keywords in specific issues text
        LOW: Tangential match only

    Args:
        filing: Normalized filing dict
        govt_entities: List of government entity names from activities
        covered_positions: List of lobbyist covered position dicts

    Returns:
        (score, reason) tuple
    """
    reasons = []

    # Check for foreign entity + VA (CRITICAL)
    if filing.get("foreign_entity_listed"):
        reasons.append("foreign_entity_va_target")

    # Check covered positions for VA keywords (CRITICAL)
    for pos in covered_positions:
        pos_text = pos.get("covered_position", "").lower()
        for keyword in VA_COVERED_POSITION_KEYWORDS:
            if keyword in pos_text:
                reasons.append(f"revolving_door:{pos.get('name', 'unknown')}")
                break

    if reasons:
        return "CRITICAL", "; ".join(reasons)

    # Check for direct VA entity targeting (HIGH)
    va_entity_match = any(
        "veterans" in e.lower() or "va " in e.lower() + " " for e in govt_entities
    )
    if va_entity_match:
        reasons.append("va_entity_targeted")

    # New registration targeting VA (HIGH)
    if filing.get("filing_type") in REGISTRATION_TYPES and va_entity_match:
        reasons.append("new_registration_va")

    if reasons:
        return "HIGH", "; ".join(reasons)

    # Check issue codes for VET (MEDIUM)
    issues_json = filing.get("lobbying_issues_json", "")
    if issues_json and VET_ISSUE_CODE in issues_json:
        reasons.append("vet_issue_code")

    # Check specific issues text for VA keywords (MEDIUM)
    specific_text = (filing.get("specific_issues_text") or "").lower()
    for keyword in VA_KEYWORDS:
        if keyword in specific_text:
            reasons.append(f"keyword:{keyword.strip()}")
            break

    if reasons:
        return "MEDIUM", "; ".join(reasons)

    return "LOW", "tangential_match"


def evaluate_alerts(filing: dict) -> list[dict]:
    """
    Evaluate a filing for alert conditions.

    Returns:
        List of alert dicts ready for insert_lda_alert()
    """
    alerts = []
    now_iso = datetime.now(UTC).isoformat()

    filing_type = filing.get("filing_type", "")
    relevance = filing.get("va_relevance_score", "LOW")

    # New registration targeting VA
    if filing_type in REGISTRATION_TYPES and relevance in ("HIGH", "CRITICAL"):
        alerts.append(
            {
                "filing_uuid": filing["filing_uuid"],
                "alert_type": "new_registration",
                "severity": "HIGH",
                "summary": f"New lobbyist registration: {filing['registrant_name']} for {filing['client_name']}",
                "details_json": json.dumps(
                    {
                        "registrant": filing["registrant_name"],
                        "client": filing["client_name"],
                        "relevance": relevance,
                    }
                ),
                "created_at": now_iso,
            }
        )

    # Foreign entity + VA
    if filing.get("foreign_entity_listed") and relevance in ("HIGH", "CRITICAL"):
        alerts.append(
            {
                "filing_uuid": filing["filing_uuid"],
                "alert_type": "foreign_entity",
                "severity": "HIGH",
                "summary": f"Foreign entity lobbying VA: {filing['registrant_name']} for {filing['client_name']}",
                "details_json": json.dumps(
                    {
                        "foreign_entities": filing.get("foreign_entities_json"),
                        "registrant": filing["registrant_name"],
                    }
                ),
                "created_at": now_iso,
            }
        )

    # Revolving door (covered position at VA)
    if filing.get("covered_positions_json"):
        positions = json.loads(filing["covered_positions_json"])
        va_positions = [
            p
            for p in positions
            if any(
                kw in (p.get("covered_position", "").lower()) for kw in VA_COVERED_POSITION_KEYWORDS
            )
        ]
        if va_positions:
            alerts.append(
                {
                    "filing_uuid": filing["filing_uuid"],
                    "alert_type": "revolving_door",
                    "severity": "HIGH",
                    "summary": f"Former VA official lobbying: {va_positions[0].get('name', 'unknown')}",
                    "details_json": json.dumps({"va_positions": va_positions}),
                    "created_at": now_iso,
                }
            )

    # Amendment on tracked filing
    if filing_type in AMENDMENT_TYPES and relevance in ("MEDIUM", "HIGH", "CRITICAL"):
        alerts.append(
            {
                "filing_uuid": filing["filing_uuid"],
                "alert_type": "amendment",
                "severity": "MEDIUM",
                "summary": f"Amendment filed: {filing['registrant_name']} ({filing_type})",
                "details_json": json.dumps(
                    {
                        "filing_type": filing_type,
                        "registrant": filing["registrant_name"],
                        "client": filing["client_name"],
                    }
                ),
                "created_at": now_iso,
            }
        )

    return alerts
