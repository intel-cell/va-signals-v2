"""Cross-source correlation engine for compound threat detection.

Evaluates declarative rules against recent events from multiple data sources
(oversight, bills, hearings, federal register, state signals) and generates
compound signals when correlated activity is detected.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES_PATH = ROOT / "config" / "correlation_rules.yaml"

# Topic keywords shared with adapters
TOPIC_KEYWORDS = {
    "disability_benefits": ["disability", "benefits", "compensation", "veteran benefits"],
    "rating": ["rating", "vasrd", "schedule for rating"],
    "exam_quality": ["exam", "c&p", "medical examination", "contractor exam"],
    "claims_backlog": ["backlog", "processing", "wait time", "claims processing"],
    "appeals": ["appeal", "bva", "board of veterans"],
    "vasrd": ["vasrd", "schedule for rating disabilities"],
}

TITLE_SIMILARITY_THRESHOLD = 0.85


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CorrelationRule:
    rule_id: str
    name: str
    description: str
    source_types: list[str]
    temporal_window_hours: int
    min_topic_overlap: int
    severity_base: float
    severity_multipliers: dict[str, float] = field(default_factory=dict)
    min_source_count: int = 2  # for state_divergence


@dataclass
class MemberEvent:
    source_type: str
    event_id: str
    title: str
    timestamp: str | None
    topics: list[str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "event_id": self.event_id,
            "title": self.title,
            "timestamp": self.timestamp,
        }


@dataclass
class CompoundSignal:
    compound_id: str
    rule_id: str
    severity_score: float
    narrative: str
    temporal_window_hours: int
    member_events: list[MemberEvent]
    topics: list[str]
    created_at: str

    def to_db_dict(self) -> dict:
        return {
            "compound_id": self.compound_id,
            "rule_id": self.rule_id,
            "severity_score": self.severity_score,
            "narrative": self.narrative,
            "temporal_window_hours": self.temporal_window_hours,
            "member_events": json.dumps([e.to_dict() for e in self.member_events]),
            "topics": json.dumps(self.topics),
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CorrelationEngine:
    """Evaluates correlation rules across multiple data sources."""

    def __init__(self, rules_path: Path | None = None):
        self.rules = self._load_rules(rules_path or DEFAULT_RULES_PATH)

    # -- Rule loading -------------------------------------------------------

    def _load_rules(self, path: Path) -> list[CorrelationRule]:
        if not path.exists():
            return []
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        rules = []
        for item in raw:
            rules.append(
                CorrelationRule(
                    rule_id=item["rule_id"],
                    name=item["name"],
                    description=item.get("description", ""),
                    source_types=item["source_types"],
                    temporal_window_hours=item["temporal_window_hours"],
                    min_topic_overlap=item.get("min_topic_overlap", 1),
                    severity_base=item["severity_base"],
                    severity_multipliers=item.get("severity_multipliers", {}),
                    min_source_count=item.get("min_source_count", 2),
                )
            )
        return rules

    # -- Event fetching -----------------------------------------------------

    def _extract_topics(self, title: str, extra: str = "") -> list[str]:
        combined = f"{title} {extra}".lower()
        topics = []
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(kw in combined for kw in keywords):
                topics.append(topic)
        return topics

    def _fetch_recent_events(self, hours: int) -> dict[str, list[MemberEvent]]:
        from src.db import connect, execute

        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        result: dict[str, list[MemberEvent]] = {
            "oversight": [],
            "bill": [],
            "hearing": [],
            "federal_register": [],
            "state": [],
        }
        con = connect()
        try:
            # Oversight events
            cur = execute(
                con,
                """
                SELECT event_id, event_type, theme, primary_source_type,
                       pub_timestamp, title, summary, is_escalation
                FROM om_events
                WHERE created_at >= :cutoff OR pub_timestamp >= :cutoff
                ORDER BY pub_timestamp DESC
            """,
                {"cutoff": cutoff},
            )
            for row in cur.fetchall():
                topics = self._extract_topics(row[5] or "", f"{row[6] or ''} {row[2] or ''}")
                result["oversight"].append(
                    MemberEvent(
                        source_type="oversight",
                        event_id=row[0],
                        title=row[5] or "",
                        timestamp=row[4],
                        topics=topics,
                        metadata={
                            "event_type": row[1],
                            "theme": row[2],
                            "primary_source_type": row[3],
                            "is_escalation": bool(row[7]),
                        },
                    )
                )

            # Bills
            cur = execute(
                con,
                """
                SELECT bill_id, title, policy_area, introduced_date, latest_action_date
                FROM bills
                WHERE updated_at >= :cutoff OR introduced_date >= :cutoff
                ORDER BY introduced_date DESC
            """,
                {"cutoff": cutoff},
            )
            for row in cur.fetchall():
                topics = self._extract_topics(row[1] or "", row[2] or "")
                result["bill"].append(
                    MemberEvent(
                        source_type="bill",
                        event_id=row[0],
                        title=row[1] or "",
                        timestamp=row[3],
                        topics=topics,
                        metadata={"policy_area": row[2]},
                    )
                )

            # Hearings
            cur = execute(
                con,
                """
                SELECT event_id, title, hearing_date, committee_name, status
                FROM hearings
                WHERE updated_at >= :cutoff OR hearing_date >= :cutoff
                ORDER BY hearing_date DESC
            """,
                {"cutoff": cutoff},
            )
            for row in cur.fetchall():
                topics = self._extract_topics(row[1] or "", row[3] or "")
                result["hearing"].append(
                    MemberEvent(
                        source_type="hearing",
                        event_id=row[0],
                        title=row[1] or "",
                        timestamp=row[2],
                        topics=topics,
                        metadata={"committee_name": row[3], "status": row[4]},
                    )
                )

            # Federal Register
            cur = execute(
                con,
                """
                SELECT doc_id, title, published_date, document_type
                FROM fr_seen
                WHERE first_seen_at >= :cutoff OR published_date >= :cutoff
                ORDER BY published_date DESC
            """,
                {"cutoff": cutoff},
            )
            for row in cur.fetchall():
                topics = self._extract_topics(row[1] or "", row[3] or "")
                result["federal_register"].append(
                    MemberEvent(
                        source_type="federal_register",
                        event_id=row[0],
                        title=row[1] or "",
                        timestamp=row[2],
                        topics=topics,
                        metadata={"document_type": row[3]},
                    )
                )

            # State signals
            cur = execute(
                con,
                """
                SELECT signal_id, state, title, content, pub_date
                FROM state_signals
                WHERE fetched_at >= :cutoff OR pub_date >= :cutoff
                ORDER BY pub_date DESC
            """,
                {"cutoff": cutoff},
            )
            for row in cur.fetchall():
                topics = self._extract_topics(row[2] or "", row[3] or "")
                result["state"].append(
                    MemberEvent(
                        source_type="state",
                        event_id=row[0],
                        title=row[2] or "",
                        timestamp=row[4],
                        topics=topics,
                        metadata={"state": row[1]},
                    )
                )

        finally:
            con.close()

        return result

    # -- Topic overlap ------------------------------------------------------

    def _title_word_set(self, title: str) -> set[str]:
        stopwords = {"the", "a", "an", "of", "on", "in", "to", "for", "and", "or", "is", "at", "by"}
        words = set(re.findall(r"[a-z]+", title.lower()))
        return words - stopwords

    def _title_similarity(self, titles_a: list[str], titles_b: list[str]) -> float:
        words_a: set[str] = set()
        words_b: set[str] = set()
        for t in titles_a:
            words_a |= self._title_word_set(t)
        for t in titles_b:
            words_b |= self._title_word_set(t)
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union) if union else 0.0

    def _find_topic_overlap(
        self,
        events_a: list[MemberEvent],
        events_b: list[MemberEvent],
    ) -> list[str]:
        topics_a: set[str] = set()
        topics_b: set[str] = set()
        for ev in events_a:
            topics_a.update(ev.topics)
        for ev in events_b:
            topics_b.update(ev.topics)

        overlap = sorted(topics_a & topics_b)

        # Title similarity fallback
        if not overlap:
            sim = self._title_similarity(
                [e.title for e in events_a],
                [e.title for e in events_b],
            )
            if sim >= TITLE_SIMILARITY_THRESHOLD:
                overlap.append("title_match")

        return overlap

    # -- Severity -----------------------------------------------------------

    def _compute_severity(
        self,
        rule: CorrelationRule,
        matched_events: list[MemberEvent],
        topics: list[str],
    ) -> float:
        score = rule.severity_base

        # Topic overlap bonus
        bonus = rule.severity_multipliers.get("topic_overlap_bonus", 0)
        if bonus and len(topics) > 1:
            score += bonus * (len(topics) - 1)

        # Escalation bonus
        esc_bonus = rule.severity_multipliers.get("escalation_bonus", 0)
        if esc_bonus:
            for ev in matched_events:
                if ev.metadata.get("is_escalation"):
                    score += esc_bonus
                    break

        # Source count bonus (for state_divergence)
        sc_bonus = rule.severity_multipliers.get("source_count_bonus", 0)
        if sc_bonus:
            unique_sources = len({ev.metadata.get("state", ev.event_id) for ev in matched_events})
            if unique_sources > rule.min_source_count:
                score += sc_bonus * (unique_sources - rule.min_source_count)

        return min(score, 1.0)

    # -- Narrative ----------------------------------------------------------

    def _generate_narrative(
        self,
        rule: CorrelationRule,
        matched_events: list[MemberEvent],
        topics: list[str],
    ) -> str:
        source_types = sorted({e.source_type for e in matched_events})
        titles = [e.title for e in matched_events[:3]]
        topic_str = ", ".join(topics) if topics else "general"

        parts = [
            f"[{rule.name}]",
            f"Correlated {len(matched_events)} events across {', '.join(source_types)}.",
            f"Shared topics: {topic_str}.",
            f"Window: {rule.temporal_window_hours}h.",
        ]
        if titles:
            parts.append(f"Key events: {'; '.join(titles)}.")

        return " ".join(parts)

    # -- Compound ID --------------------------------------------------------

    def _make_compound_id(
        self, rule_id: str, event_ids: list[str], topics: list[str] | None = None
    ) -> str:
        parts = [rule_id, "|".join(sorted(event_ids))]
        if topics:
            parts.append("|".join(sorted(topics)))
        key = ":".join(parts)
        return f"cs-{hashlib.sha256(key.encode()).hexdigest()[:16]}"

    # -- Rule evaluation ----------------------------------------------------

    def _evaluate_cross_source_rule(
        self,
        rule: CorrelationRule,
        events_by_source: dict[str, list[MemberEvent]],
    ) -> list[CompoundSignal]:
        """Evaluate a rule that correlates events across 2+ source types."""
        source_types = rule.source_types
        available = [st for st in source_types if events_by_source.get(st)]
        if len(available) < 2:
            return []

        # Pair-wise comparison between all source type combinations
        signals = []
        seen_ids: set[str] = set()

        for i, st_a in enumerate(available):
            for st_b in available[i + 1 :]:
                events_a = events_by_source[st_a]
                events_b = events_by_source[st_b]
                topics = self._find_topic_overlap(events_a, events_b)
                if len(topics) < rule.min_topic_overlap:
                    continue

                matched = events_a + events_b
                event_ids = [e.event_id for e in matched]
                cid = self._make_compound_id(rule.rule_id, event_ids)
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)

                severity = self._compute_severity(rule, matched, topics)
                narrative = self._generate_narrative(rule, matched, topics)

                signals.append(
                    CompoundSignal(
                        compound_id=cid,
                        rule_id=rule.rule_id,
                        severity_score=severity,
                        narrative=narrative,
                        temporal_window_hours=rule.temporal_window_hours,
                        member_events=matched,
                        topics=topics,
                        created_at=datetime.now(UTC).isoformat(),
                    )
                )

        return signals

    def _evaluate_divergence_rule(
        self,
        rule: CorrelationRule,
        events_by_source: dict[str, list[MemberEvent]],
    ) -> list[CompoundSignal]:
        """Evaluate state_divergence: N+ events from different states sharing topics."""
        source_type = rule.source_types[0]  # "state"
        events = events_by_source.get(source_type, [])
        if len(events) < rule.min_source_count:
            return []

        # Group by topic
        topic_events: dict[str, list[MemberEvent]] = {}
        for ev in events:
            for topic in ev.topics:
                topic_events.setdefault(topic, []).append(ev)

        signals = []
        for topic, evts in topic_events.items():
            # Count unique states
            states = {ev.metadata.get("state") for ev in evts}
            if len(states) < rule.min_source_count:
                continue

            event_ids = [e.event_id for e in evts]
            topics = [topic]
            cid = self._make_compound_id(rule.rule_id, event_ids, topics)
            severity = self._compute_severity(rule, evts, topics)
            narrative = self._generate_narrative(rule, evts, topics)

            signals.append(
                CompoundSignal(
                    compound_id=cid,
                    rule_id=rule.rule_id,
                    severity_score=severity,
                    narrative=narrative,
                    temporal_window_hours=rule.temporal_window_hours,
                    member_events=evts,
                    topics=topics,
                    created_at=datetime.now(UTC).isoformat(),
                )
            )

        return signals

    def evaluate_rules(self) -> list[CompoundSignal]:
        """Evaluate all rules against recent events."""
        # Determine the max window across all rules
        max_hours = max((r.temporal_window_hours for r in self.rules), default=168)
        events_by_source = self._fetch_recent_events(max_hours)

        all_signals: list[CompoundSignal] = []
        for rule in self.rules:
            if rule.rule_id == "state_divergence":
                all_signals.extend(self._evaluate_divergence_rule(rule, events_by_source))
            else:
                all_signals.extend(self._evaluate_cross_source_rule(rule, events_by_source))

        return all_signals

    # -- Main entry ---------------------------------------------------------

    def run(self) -> dict:
        """Evaluate rules, store results, return summary."""
        from src.db.compound import insert_compound_signal

        signals = self.evaluate_rules()
        stored = 0
        by_rule: dict[str, int] = {}

        for sig in signals:
            result = insert_compound_signal(sig.to_db_dict())
            if result is not None:
                stored += 1
            by_rule[sig.rule_id] = by_rule.get(sig.rule_id, 0) + 1

        return {
            "total_signals": len(signals),
            "stored": stored,
            "by_rule": by_rule,
        }
