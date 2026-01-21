"""Common utilities for State Intelligence module."""

import hashlib
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class RawSignal:
    """Raw signal from a state source."""

    url: str
    title: str
    source_id: str
    state: str
    content: Optional[str] = None
    pub_date: Optional[str] = None
    event_date: Optional[str] = None
    metadata: Optional[dict] = None


def generate_signal_id(url: str) -> str:
    """Generate deterministic signal ID from URL."""
    return hashlib.sha256(url.encode()).hexdigest()


# --- Program detection ---

PROGRAM_PATTERNS = {
    "pact_act": [
        r"pact act",
        r"toxic exposure",
        r"burn pit",
        r"presumptive condition",
    ],
    "community_care": [
        r"community care",
        r"choice program",
        r"mission act",
        r"provider network",
        r"ccn",
    ],
    "vha": [
        r"veterans health administration",
        r"vha",
        r"va hospital",
        r"va medical center",
        r"vamc",
        r"va facility",
    ],
}


def detect_program(text: str) -> Optional[str]:
    """Detect which federal program a signal relates to."""
    text_lower = text.lower()

    for program, patterns in PROGRAM_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return program

    return None


# --- Veteran relevance ---

VETERAN_KEYWORDS = [
    "veteran",
    "veterans",
    "va ",
    "v.a.",
    "military",
    "service member",
    "servicemember",
    "armed forces",
    "calvet",
    "tvc",
    "floridavets",
]


def is_veteran_relevant(text: str) -> bool:
    """Check if text is relevant to veterans."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in VETERAN_KEYWORDS)
