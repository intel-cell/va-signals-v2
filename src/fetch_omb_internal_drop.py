"""
OMB Internal Drop folder scanner for Authority Layer.

Scans data/omb_apportionments/ folder for manually-dropped PDFs and files.
Computes hashes for change detection and stores metadata.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Root of the project
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DROP_FOLDER = ROOT / "data" / "omb_apportionments"

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt", ".csv"}


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file content."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks for large files
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]


def _generate_doc_id(file_path: Path) -> str:
    """Generate a stable doc_id from file path."""
    # Use relative path from drop folder and sanitize
    name = file_path.stem.lower()
    name = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)
    name = name[:50]
    return f"omb-drop-{name}"


def _extract_date_from_filename(filename: str) -> Optional[str]:
    """Try to extract a date from the filename."""
    import re

    # Common date patterns in filenames
    patterns = [
        # 2026-01-29
        (r"(\d{4})-(\d{2})-(\d{2})", "%Y-%m-%d"),
        # 20260129
        (r"(\d{4})(\d{2})(\d{2})", "%Y%m%d"),
        # 01-29-2026
        (r"(\d{2})-(\d{2})-(\d{4})", "%m-%d-%Y"),
        # FY2026, FY26
        (r"FY\s*(\d{4})", None),
        (r"FY\s*(\d{2})", None),
    ]

    for pattern, date_fmt in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            if date_fmt:
                try:
                    date_str = match.group(0)
                    dt = datetime.strptime(date_str, date_fmt)
                    return dt.replace(tzinfo=timezone.utc).isoformat()
                except ValueError:
                    continue
            else:
                # FY pattern - return fiscal year start
                year = match.group(1)
                if len(year) == 2:
                    year = f"20{year}"
                return f"{year}-10-01T00:00:00+00:00"

    return None


def _classify_doc_type(filename: str) -> str:
    """Classify document type based on filename."""
    filename_lower = filename.lower()

    if "apportionment" in filename_lower:
        return "apportionment"
    elif "allotment" in filename_lower:
        return "allotment"
    elif "budget" in filename_lower:
        return "budget"
    elif "passback" in filename_lower:
        return "passback"
    elif "guidance" in filename_lower:
        return "guidance"
    elif "memo" in filename_lower:
        return "memorandum"
    else:
        return "internal_document"


def scan_omb_drop_folder(
    drop_folder: Path = None,
    include_all: bool = False,
) -> list[dict]:
    """
    Scan OMB drop folder for documents.

    Args:
        drop_folder: Path to drop folder (defaults to data/omb_apportionments/)
        include_all: Include all files regardless of extension

    Returns:
        List of dicts ready for upsert_authority_doc()
    """
    if drop_folder is None:
        drop_folder = DEFAULT_DROP_FOLDER

    docs = []

    # Create folder if it doesn't exist
    drop_folder.mkdir(parents=True, exist_ok=True)

    # Scan all files in the folder (including subdirectories)
    for file_path in drop_folder.rglob("*"):
        if not file_path.is_file():
            continue

        # Skip hidden files
        if file_path.name.startswith("."):
            continue

        # Check extension
        ext = file_path.suffix.lower()
        if not include_all and ext not in SUPPORTED_EXTENSIONS:
            continue

        try:
            stat = file_path.stat()
            file_modified = datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat()

            content_hash = _compute_file_hash(file_path)

            # Generate relative path for display
            try:
                rel_path = file_path.relative_to(drop_folder)
            except ValueError:
                rel_path = file_path.name

            doc = {
                "doc_id": _generate_doc_id(file_path),
                "authority_source": "omb_internal",
                "authority_type": _classify_doc_type(file_path.name),
                "title": file_path.name,
                "published_at": _extract_date_from_filename(file_path.name),
                "source_url": f"file://{file_path}",
                "body_text": None,  # Binary files - text extraction would need separate processing
                "content_hash": content_hash,
                "metadata_json": json.dumps({
                    "file_path": str(file_path),
                    "relative_path": str(rel_path),
                    "file_size": stat.st_size,
                    "file_modified": file_modified,
                    "extension": ext,
                }),
            }
            docs.append(doc)

        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            continue

    return docs


if __name__ == "__main__":
    # Test run
    docs = scan_omb_drop_folder()
    print(f"Found {len(docs)} documents in drop folder:")
    for doc in docs:
        meta = json.loads(doc["metadata_json"])
        print(f"  [{doc['authority_type']}] {doc['title']} ({meta['file_size']} bytes)")
