import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import requests

HEADERS_JSON = {"Accept": "application/json"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_json_listing_url(bulk_url: str) -> str:
    if "/bulkdata/json/" in bulk_url:
        return bulk_url
    if "/bulkdata/" not in bulk_url:
        return bulk_url
    return bulk_url.replace("/bulkdata/", "/bulkdata/json/", 1)


def _to_bulk_url(json_or_bulk_url: str) -> str:
    return json_or_bulk_url.replace("/bulkdata/json/", "/bulkdata/", 1)


def fetch_bulk_listing_json(bulk_url: str, timeout: int = 30) -> Dict[str, Any]:
    url = _to_json_listing_url(bulk_url)
    r = requests.get(url, headers=HEADERS_JSON, timeout=timeout)
    r.raise_for_status()
    return r.json()


def list_folder_children(bulk_url: str, timeout: int = 30) -> List[Dict[str, Any]]:
    data = fetch_bulk_listing_json(bulk_url, timeout=timeout)
    files = data.get("files") or data.get("file") or []
    return list(files) if isinstance(files, (list, tuple)) else []


def _is_folder(item: Dict[str, Any]) -> bool:
    return bool(item.get("folder"))


def _label(item: Dict[str, Any]) -> str:
    return str(item.get("displayLabel") or item.get("name") or "").strip()


def list_latest_month_folders(fr_root_bulk_url: str, max_months: int = 3, timeout: int = 30) -> List[Tuple[str, str]]:
    """Return newest-first list of (YYYY-MM, month_bulk_url)."""
    out: List[Tuple[str, str]] = []

    years_items = [i for i in list_folder_children(fr_root_bulk_url, timeout=timeout) if _is_folder(i)]
    years: List[Tuple[str, str]] = []
    for it in years_items:
        lab = _label(it)
        link = it.get("link")
        if lab.isdigit() and link:
            years.append((lab, link))
    years.sort(key=lambda x: x[0], reverse=True)

    for y, year_link in years:
        if len(out) >= max_months:
            break

        months_items = [i for i in list_folder_children(year_link, timeout=timeout) if _is_folder(i)]
        months: List[Tuple[str, str]] = []
        for it in months_items:
            lab = _label(it)
            link = it.get("link")
            if re.fullmatch(r"\d{2}", lab) and link:
                months.append((lab, link))
        months.sort(key=lambda x: x[0], reverse=True)

        for m, month_link in months:
            if len(out) >= max_months:
                break
            out.append((f"{y}-{m}", _to_bulk_url(month_link)))

    return out


def list_month_packages(month_bulk_url: str, timeout: int = 30) -> List[Dict[str, str]]:
    """Return FR package IDs in a month folder (FR-YYYY-MM-DD*)."""
    items = list_folder_children(month_bulk_url, timeout=timeout)
    out: List[Dict[str, str]] = []
    for it in items:
        lab = _label(it)
        link = it.get("link") or ""
        m = re.match(r"^FR-(\d{4})-(\d{2})-(\d{2})", lab)
        if m:
            published_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            out.append({
                "doc_id": lab.strip("/"),
                "published_date": published_date,
                "source_url": link or month_bulk_url,
            })
    return out
