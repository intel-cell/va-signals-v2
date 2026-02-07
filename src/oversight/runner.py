"""CLI runner for oversight monitor - orchestrates agents and pipeline."""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from .agents.gao import GAOAgent
from .agents.oig import OIGAgent
from .agents.crs import CRSAgent
from .agents.congressional_record import CongressionalRecordAgent
from .agents.committee_press import CommitteePressAgent
from .agents.news_wire import NewsWireAgent
from .agents.investigative import InvestigativeAgent
from .agents.trade_press import TradePressAgent
from .agents.cafc import CAFCAgent
from .agents.bva import BVAAgent
from .agents.base import RawEvent, TimestampResult
from .db_helpers import (
    insert_om_event,
    get_om_event,
    insert_om_rejected,
    get_om_events_for_digest,
    seed_default_escalation_signals,
)
from .pipeline.quality_gate import check_quality_gate
from .pipeline.escalation import check_escalation
from .pipeline.deduplicator import deduplicate_event, extract_entities
from .output.formatters import format_weekly_digest


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Registry of available agents
AGENT_REGISTRY = {
    "gao": GAOAgent,
    "oig": OIGAgent,
    "crs": CRSAgent,
    "congressional_record": CongressionalRecordAgent,
    "committee_press": CommitteePressAgent,
    "news_wire": NewsWireAgent,
    "investigative": InvestigativeAgent,
    "trade_press": TradePressAgent,
    "cafc": CAFCAgent,
    "bva": BVAAgent,
}


@dataclass
class OversightRunResult:
    """Result of running an oversight agent."""

    agent: str
    status: str  # SUCCESS, NO_DATA, ERROR
    events_fetched: int = 0
    events_processed: int = 0
    escalations: int = 0
    deviations: int = 0
    errors: list = field(default_factory=list)


_THEME_KEYWORDS = {
    "oversight_report": ["report", "audit", "review", "assessment", "evaluation"],
    "congressional_action": ["hearing", "committee", "subcommittee", "legislation", "bill", "resolution"],
    "legal_ruling": ["ruling", "decision", "opinion", "court", "judge", "appeal"],
    "policy_change": ["policy", "regulation", "rule", "guidance", "directive", "memorandum"],
    "budget_fiscal": ["budget", "funding", "appropriation", "fiscal", "spending"],
    "personnel": ["appoint", "resign", "nominee", "director", "secretary", "leadership"],
    "healthcare_operations": ["hospital", "clinic", "wait time", "staffing", "facility"],
    "benefits_claims": ["claim", "benefit", "disability", "compensation", "pension"],
}

_SOURCE_TYPE_THEME_MAP = {
    "gao": "oversight_report",
    "oig": "oversight_report",
    "congressional_record": "congressional_action",
    "committee_press": "congressional_action",
    "cafc": "legal_ruling",
    "bva": "legal_ruling",
}


def _extract_theme(title: str, source_type: str) -> Optional[str]:
    """Extract theme from title keywords, falling back to source_type mapping."""
    lower_title = title.lower()
    for theme, keywords in _THEME_KEYWORDS.items():
        for kw in keywords:
            if kw in lower_title:
                return theme
    return _SOURCE_TYPE_THEME_MAP.get(source_type)


def _generate_event_id(source_type: str, url: str) -> str:
    """Generate a deterministic event ID."""
    hash_input = f"{source_type}:{url}"
    return f"om-{source_type}-{hashlib.sha256(hash_input.encode()).hexdigest()[:12]}"


def _process_raw_event(
    raw: RawEvent,
    agent,
    source_type: str,
) -> tuple[Optional[dict], Optional[str]]:
    """
    Process a raw event through the pipeline.

    Returns:
        (event_dict, rejection_reason) - event_dict is None if rejected
    """
    # Extract timestamps
    timestamps = agent.extract_timestamps(raw)

    # Quality gate
    qg_result = check_quality_gate(timestamps, raw.url)
    if not qg_result.passed:
        return None, qg_result.rejection_reason

    # Extract entities for deduplication
    entities = extract_entities(raw.title, raw.raw_html, raw.url)
    canonical_refs = agent.extract_canonical_refs(raw)
    entities.update(canonical_refs)

    # Check for duplicates
    dedup_result = deduplicate_event(
        title=raw.title,
        content=raw.raw_html,
        url=raw.url,
        source_type=source_type,
        pub_timestamp=timestamps.pub_timestamp,
    )

    if dedup_result.is_duplicate:
        return None, "duplicate"

    # Check for escalation signals
    esc_result = check_escalation(raw.title, raw.raw_html)

    # Generate event ID
    event_id = _generate_event_id(source_type, raw.url)

    # Build event dict
    event = {
        "event_id": event_id,
        "event_type": "report_release",  # Default, can be overridden
        "theme": _extract_theme(raw.title, source_type),
        "primary_source_type": source_type,
        "primary_url": raw.url,
        "pub_timestamp": timestamps.pub_timestamp,
        "pub_precision": timestamps.pub_precision,
        "pub_source": timestamps.pub_source,
        "event_timestamp": timestamps.event_timestamp,
        "event_precision": timestamps.event_precision,
        "event_source": timestamps.event_source,
        "title": raw.title,
        "summary": raw.excerpt,
        "raw_content": raw.raw_html[:5000] if raw.raw_html else None,
        "is_escalation": esc_result.is_escalation,
        "escalation_signals": esc_result.matched_signals if esc_result.is_escalation else None,
        "ml_score": esc_result.ml_score,
        "ml_risk_level": esc_result.ml_risk_level,
        "is_deviation": 0,  # Will be set by deviation classifier
        "deviation_reason": None,
        "canonical_refs": entities if entities else None,
        "fetched_at": raw.fetched_at,
    }

    return event, None


def run_agent(agent_name: str, since: Optional[datetime] = None) -> OversightRunResult:
    """
    Run a single oversight agent.

    Args:
        agent_name: Name of agent to run
        since: Only fetch events since this time

    Returns:
        OversightRunResult with stats
    """
    if agent_name not in AGENT_REGISTRY:
        return OversightRunResult(
            agent=agent_name,
            status="ERROR",
            errors=[f"Unknown agent: {agent_name}"],
        )

    try:
        # Initialize agent
        agent_class = AGENT_REGISTRY[agent_name]
        agent = agent_class()

        # Fetch events
        raw_events = agent.fetch_new(since=since)
        logger.info(f"[{agent_name}] Fetched {len(raw_events)} events")

        if not raw_events:
            return OversightRunResult(
                agent=agent_name,
                status="NO_DATA",
                events_fetched=0,
            )

        # Process events
        processed = 0
        escalations = 0
        errors = []

        for raw in raw_events:
            try:
                event, rejection_reason = _process_raw_event(raw, agent, agent_name)

                if rejection_reason:
                    insert_om_rejected({
                        "source_type": agent_name,
                        "url": raw.url,
                        "title": raw.title,
                        "pub_timestamp": None,
                        "rejection_reason": rejection_reason,
                        "fetched_at": raw.fetched_at,
                    })
                    continue

                # Check if already exists
                existing = get_om_event(event["event_id"])
                if existing:
                    continue

                # Insert event
                insert_om_event(event)
                processed += 1

                if event.get("is_escalation"):
                    escalations += 1

            except Exception as e:
                errors.append(f"Error processing {raw.url}: {str(e)}")
                logger.error(f"Error processing event: {e}")

        return OversightRunResult(
            agent=agent_name,
            status="SUCCESS" if processed > 0 else "NO_DATA",
            events_fetched=len(raw_events),
            events_processed=processed,
            escalations=escalations,
            deviations=0,
            errors=errors,
        )

    except Exception as e:
        logger.error(f"Agent {agent_name} failed: {e}")
        return OversightRunResult(
            agent=agent_name,
            status="ERROR",
            errors=[str(e)],
        )


def run_all_agents(since: Optional[datetime] = None) -> list[OversightRunResult]:
    """
    Run all registered oversight agents in parallel using ThreadPoolExecutor.

    Args:
        since: Only fetch events since this time

    Returns:
        List of results for each agent (in registry order)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    agent_results: dict[str, OversightRunResult] = {}

    with ThreadPoolExecutor(max_workers=len(AGENT_REGISTRY)) as executor:
        future_to_agent = {
            executor.submit(run_agent, agent_name, since): agent_name
            for agent_name in AGENT_REGISTRY
        }
        for future in as_completed(future_to_agent):
            agent_name = future_to_agent[future]
            try:
                result = future.result()
                agent_results[agent_name] = result
                logger.info(f"[{agent_name}] {result.status}: {result.events_processed} processed")
            except Exception as e:
                logger.error(f"[{agent_name}] Thread failed: {e}")
                agent_results[agent_name] = OversightRunResult(
                    agent=agent_name,
                    status="ERROR",
                    errors=[f"Thread exception: {repr(e)}"],
                )

    # Return in registry order for deterministic output
    return [agent_results[name] for name in AGENT_REGISTRY]


def run_backfill(
    agent_name: str,
    start_date: str,
    end_date: str,
) -> OversightRunResult:
    """
    Backfill historical data for an agent.

    Args:
        agent_name: Agent to backfill
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        OversightRunResult with stats
    """
    if agent_name not in AGENT_REGISTRY:
        return OversightRunResult(
            agent=agent_name,
            status="ERROR",
            errors=[f"Unknown agent: {agent_name}"],
        )

    try:
        agent_class = AGENT_REGISTRY[agent_name]
        agent = agent_class()

        start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)

        raw_events = agent.backfill(start, end)
        logger.info(f"[{agent_name}] Backfill fetched {len(raw_events)} events")

        # Process same as normal run
        processed = 0
        for raw in raw_events:
            event, rejection_reason = _process_raw_event(raw, agent, agent_name)
            if event:
                existing = get_om_event(event["event_id"])
                if not existing:
                    insert_om_event(event)
                    processed += 1

        return OversightRunResult(
            agent=agent_name,
            status="SUCCESS" if processed > 0 else "NO_DATA",
            events_fetched=len(raw_events),
            events_processed=processed,
        )

    except Exception as e:
        return OversightRunResult(
            agent=agent_name,
            status="ERROR",
            errors=[str(e)],
        )


def generate_digest(
    start_date: str,
    end_date: str,
    output_format: str = "markdown",
) -> str:
    """
    Generate a digest of events for a period.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        output_format: "markdown" (default)

    Returns:
        Formatted digest string (markdown)
    """
    events = get_om_events_for_digest(start_date, end_date)

    return format_weekly_digest(
        events=events,
        period_start=start_date,
        period_end=end_date,
    )


def init_oversight():
    """Initialize oversight system - seed defaults, etc."""
    seed_default_escalation_signals()
    logger.info("Oversight system initialized")
