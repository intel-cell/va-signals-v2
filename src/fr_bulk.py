import re
from datetime import datetime, timezone
from typing import List, Dict, Any
import requests

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def fetch_fr_listing(endpoint: str, timeout: int = 30) -> str:
    r = requests.get(endpoint, timeout=timeout)
    r.raise_for_status()
    return r.text

def parse_listing_for_dates(html: str) -> List[str]:
    # GovInfo bulk listing includes date-like directory names (YYYY/MM/DD/)
    dates = set(re.findall(r'href="(\\d{4}/\\d{2}/\\d{2}/)"', html))
    return sorted(dates, reverse=True)

def build_date_url(base: str, ymd: str) -> str:
    return base.rstrip("/") + "/" + ymd

def fetch_fr_date_index(date_url: str, timeout: int = 30) -> str:
    r = requests.get(date_url, timeout=timeout)
    r.raise_for_status()
    return r.text

def parse_date_index_for_packages(html: str) -> List[str]:
    # Package IDs look like: FR-2026-01-12 (pattern may vary; keep permissive)
    # GovInfo bulk pages commonly list package folders / links; capture href targets
    pkgs = set(re.findall(r'href="([^"]+)"', html))
    # Keep only likely package ids / folders
    keep = []
    for p in pkgs:
        if p.startswith("FR-") or p.startswith("FR"):
            keep.append(p.strip("/"))
    return sorted(set(keep))

