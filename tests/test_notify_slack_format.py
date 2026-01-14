from src.notify_slack import format_fr_delta_alert

def test_format_alert_none_on_no_data():
    assert format_fr_delta_alert({"status": "NO_DATA"}, []) is None

def test_format_alert_error():
    p = format_fr_delta_alert({"status": "ERROR", "source_id": "govinfo_fr_bulk", "records_fetched": 0, "errors": ["x"]}, [])
    assert p and "ERROR" in p["text"]

def test_format_alert_new_docs_includes_doc_ids_and_links():
    docs = [
        {"doc_id": "FR-2026-01-13.xml", "source_url": "https://www.govinfo.gov/bulkdata/FR/2026/01/FR-2026-01-13.xml"},
        {"doc_id": "FR-2026-01-12.xml", "source_url": "https://www.govinfo.gov/bulkdata/FR/2026/01/FR-2026-01-12.xml"},
    ]
    p = format_fr_delta_alert({"status": "SUCCESS", "source_id": "govinfo_fr_bulk", "records_fetched": 46, "errors": []}, docs)
    assert p and "FR-2026-01-13.xml" in p["text"] and "https://www.govinfo.gov/bulkdata/FR/2026/01/FR-2026-01-13.xml" in p["text"]
