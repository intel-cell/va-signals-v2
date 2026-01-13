from datetime import datetime, timezone

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def require_provenance(signal: dict) -> None:
    prov = signal.get("provenance")
    if not isinstance(prov, dict):
        raise ValueError("PROVENANCE_MISSING")

    for field in ("source_id","source_name","retrieved_at","source_url_or_primary_id"):
        if not prov.get(field):
            raise ValueError(f"PROVENANCE_MISSING_FIELD: {field}")

    try:
        datetime.fromisoformat(prov["retrieved_at"].replace("Z","+00:00"))
    except Exception:
        raise ValueError("PROVENANCE_BAD_TIMESTAMP")
