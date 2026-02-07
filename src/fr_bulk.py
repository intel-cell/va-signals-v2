import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS_JSON = {"Accept": "application/json"}

# Thread-local session with retry/backoff for connection reuse and resilience
_session_local = threading.local()


def _get_session() -> requests.Session:
    """Return a thread-local session with retry strategy."""
    session = getattr(_session_local, "session", None)
    if session is None:
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(HEADERS_JSON)
        _session_local.session = session
    return session


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _to_json_listing_url(bulk_url: str) -> str:
    if "/bulkdata/json/" in bulk_url:
        return bulk_url
    if "/bulkdata/" not in bulk_url:
        return bulk_url
    return bulk_url.replace("/bulkdata/", "/bulkdata/json/", 1)


def _to_bulk_url(json_or_bulk_url: str) -> str:
    return json_or_bulk_url.replace("/bulkdata/json/", "/bulkdata/", 1)


def fetch_bulk_listing_json(bulk_url: str, timeout: int = 30) -> dict[str, Any]:
    url = _to_json_listing_url(bulk_url)
    r = _get_session().get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def list_folder_children(bulk_url: str, timeout: int = 30) -> list[dict[str, Any]]:
    data = fetch_bulk_listing_json(bulk_url, timeout=timeout)
    files = data.get("files") or data.get("file") or []
    return list(files) if isinstance(files, (list, tuple)) else []


def _is_folder(item: dict[str, Any]) -> bool:
    return bool(item.get("folder"))


def _label(item: dict[str, Any]) -> str:
    return str(item.get("displayLabel") or item.get("name") or "").strip()


def list_latest_month_folders(
    fr_root_bulk_url: str, max_months: int = 3, timeout: int = 30
) -> list[tuple[str, str]]:
    """Return newest-first list of (YYYY-MM, month_bulk_url)."""
    out: list[tuple[str, str]] = []

    years_items = [
        i for i in list_folder_children(fr_root_bulk_url, timeout=timeout) if _is_folder(i)
    ]
    years: list[tuple[str, str]] = []
    for it in years_items:
        lab = _label(it)
        link = it.get("link")
        if lab.isdigit() and link:
            years.append((lab, link))
    years.sort(key=lambda x: x[0], reverse=True)

    for y, year_link in years:
        if len(out) >= max_months:
            break

        months_items = [
            i for i in list_folder_children(year_link, timeout=timeout) if _is_folder(i)
        ]
        months: list[tuple[str, str]] = []
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


def list_month_packages(month_bulk_url: str, timeout: int = 30) -> list[dict[str, str]]:
    """Return FR package IDs in a month folder (FR-YYYY-MM-DD*)."""
    items = list_folder_children(month_bulk_url, timeout=timeout)
    out: list[dict[str, str]] = []
    for it in items:
        lab = _label(it)
        link = it.get("link") or ""
        m = re.match(r"^FR-(\d{4})-(\d{2})-(\d{2})", lab)
        if m:
            published_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            out.append(
                {
                    "doc_id": lab.strip("/"),
                    "published_date": published_date,
                    "source_url": link or month_bulk_url,
                }
            )
    return out


def list_all_packages_parallel(
    month_folders: list[tuple[str, str]], timeout: int = 30, max_workers: int = 4
) -> list[dict[str, str]]:
    """Fetch packages from multiple month folders in parallel."""
    all_packages: list[dict[str, str]] = []

    def fetch_month(month_url: str) -> list[dict[str, str]]:
        return list_month_packages(month_url, timeout=timeout)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_month = {executor.submit(fetch_month, url): label for label, url in month_folders}
        for future in as_completed(future_to_month):
            pkgs = future.result()  # Propagate exceptions for fail-closed
            all_packages.extend(pkgs)

    return all_packages
