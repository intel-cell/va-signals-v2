import pytest
from src.provenance import require_provenance

def test_provenance_missing_blocks():
    with pytest.raises(ValueError):
        require_provenance({"id": "signal-12345678"})

def test_provenance_present_passes():
    require_provenance({
        "id": "signal-12345678",
        "provenance": {
            "source_id": "govinfo_fr_bulk",
            "source_name": "GovInfo Federal Register Bulk Data",
            "retrieved_at": "2026-01-12T00:00:00+00:00",
            "source_url_or_primary_id": "https://www.govinfo.gov/bulkdata/FR/"
        }
    })
