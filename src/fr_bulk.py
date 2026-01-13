import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import requests

# GovInfo bulkdata exposes JSON directory listings by inserting `/json/` after `/bulkdata/`.
# Example: https://www.govinfo.gov/bulkdata/FR/2025/ -> https://www.govinfo.gov/bulkdata/json/FR/2025/

HEADERS_JSON = {"Accept": "application/json"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_json_listing_url(bulk_url: str) -> str:
    if "/bulkdata/json/" in bulk_url:
        return bulk_url
    if "/bulkdata/" not in bulk_url:
        return bulk_url
    return bulk_url.replace("/bulkdata/", "/bulkdata/json/", 1)


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


def list_latest_day_folders(fr_root_bulk_url: str, max_days: int = 7, timeout: int = 30) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []

    years_items = [i for i in list_folder_children(fr_root_bulk_url, timeout=timeout) if _is_folder(i)]
    years = sorted({lab for lab in (_label(i) for i in years_items) if lab.isdigit()}, reverse=True)

    for y in years:
        if len(out) >= max_days:
            break
        year_url = fr_root_bulk_url.rstrip("/") + f"/{y}/"

        months_items = [i for i in list_folder_children(year_url, timeout=timeout) if _is_folder(i)]
        months = sorted({lab for lab in (_label(i) for i in months_items) if re.fullmatch(r"\d{2}", lab)}, reverse=True)

        for m in months:
            if len(out) >= max_days:
                break
            month_url = year_url.rstrip("/") + f"/{m}/"

            days_items = [i for i in list_folder_children(month_url, timeout=timeout) if _is_folder(i)]
            days = sorted({lab for lab in (_label(i) for i in days_items) if re.fullmatch(r"\d{2}", lab)}, reverse=True)

            for d in days:
                if len(out) >= max_days:
                    break
                day_url = month_url.rstrip("/") + f"/{d}/"
                out.append((f"{y}-{m}-{d}", day_url))

    return out


def list_day_packages(day_folder_url: str, timeout: int = 30) -> List[str]:
    items = list_folder_children(day_folder_url, timeout=timeout)
    pkgs: List[str] = []
    for it in items:
        lab = _label(it)
        if lab.startswith("FR-"):
            pkgs.append(lab.strip("/"))
    return sorted(set(pkgs))
