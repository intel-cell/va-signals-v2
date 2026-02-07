"""Evidence test fixtures."""

import pytest

from src.evidence.models import (
    ClaimType,
    Confidence,
    EvidenceClaim,
    EvidenceExcerpt,
    EvidencePack,
    EvidenceSource,
    SourceType,
)


@pytest.fixture
def sample_source():
    """A valid EvidenceSource with all required fields."""
    return EvidenceSource(
        source_id=EvidenceSource.generate_source_id(SourceType.FEDERAL_REGISTER, "2024-01234"),
        source_type=SourceType.FEDERAL_REGISTER,
        title="Federal Register Document 2024-01234",
        url="https://www.federalregister.gov/d/2024-01234",
        date_accessed="2026-02-07T00:00:00+00:00",
        date_published="2026-01-15",
        fr_doc_number="2024-01234",
        fr_citation="FR Doc. 2024-01234",
        issuing_agency="Federal Register",
    )


@pytest.fixture
def sample_bill_source():
    """A valid bill EvidenceSource."""
    return EvidenceSource(
        source_id=EvidenceSource.generate_source_id(SourceType.BILL, "hr-118-100"),
        source_type=SourceType.BILL,
        title="Test VA Bill",
        url="https://www.congress.gov/bill/118th-congress/hr/100",
        date_accessed="2026-02-07T00:00:00+00:00",
        date_published="2024-01-10",
        bill_number="HR100",
        bill_congress=118,
    )


@pytest.fixture
def sample_claim(sample_source):
    """A valid EvidenceClaim with source references."""
    return EvidenceClaim(
        claim_text="VA published final rule on toxic exposure benefits",
        claim_type=ClaimType.OBSERVED,
        confidence=Confidence.HIGH,
        source_ids=[sample_source.source_id],
        last_verified="2026-02-07T00:00:00+00:00",
    )


@pytest.fixture
def sample_excerpt():
    """A valid EvidenceExcerpt."""
    return EvidenceExcerpt(
        excerpt_text="The Department of Veterans Affairs is amending its regulations",
        source_id="abc123",
        section_reference="Section 3(a)(1)",
        page_or_line="42",
    )


@pytest.fixture
def sample_pack(sample_source, sample_claim):
    """A valid EvidencePack with one source and one claim."""
    pack = EvidencePack(
        pack_id="EP-TEST-20260207120000",
        title="Test Evidence Pack",
        generated_at="2026-02-07T12:00:00+00:00",
        generated_by="test_suite",
        issue_id="TEST-001",
        summary="Test summary",
    )
    pack.add_source(sample_source)
    pack.add_claim(sample_claim)
    return pack


@pytest.fixture
def populated_db(use_test_db):
    """Insert sample FR, bills, oversight rows into test DB for extractor tests."""
    from src.db import connect, execute

    con = connect()
    try:
        # Insert FR doc
        execute(
            con,
            """
            INSERT INTO fr_seen (doc_id, published_date, source_url, first_seen_at)
            VALUES (:doc_id, :pub_date, :url, datetime('now'))
        """,
            {
                "doc_id": "2024-01234",
                "pub_date": "2026-01-15",
                "url": "https://www.federalregister.gov/d/2024-01234",
            },
        )

        # Insert FR summary
        execute(
            con,
            """
            INSERT INTO fr_summaries (doc_id, summary, bullet_points, veteran_impact, tags, summarized_at)
            VALUES (:doc_id, :summary, :bullets, :impact, :tags, datetime('now'))
        """,
            {
                "doc_id": "2024-01234",
                "summary": "Test veteran summary",
                "bullets": "- Point 1",
                "impact": "High impact on veterans",
                "tags": "veteran,benefits",
            },
        )

        # Insert bill
        execute(
            con,
            """
            INSERT INTO bills (bill_id, congress, bill_type, bill_number, title,
                sponsor_name, sponsor_bioguide_id, sponsor_party, sponsor_state,
                introduced_date, latest_action_date, latest_action_text,
                policy_area, committees_json, cosponsors_count,
                first_seen_at, updated_at)
            VALUES (:bill_id, :congress, :bill_type, :bill_number, :title,
                :sponsor_name, :sponsor_bioguide_id, :sponsor_party, :sponsor_state,
                :introduced_date, :latest_action_date, :latest_action_text,
                :policy_area, :committees_json, :cosponsors_count,
                datetime('now'), datetime('now'))
        """,
            {
                "bill_id": "hr-118-100",
                "congress": 118,
                "bill_type": "hr",
                "bill_number": 100,
                "title": "Test VA Bill",
                "sponsor_name": "Smith",
                "sponsor_bioguide_id": "S000001",
                "sponsor_party": "D",
                "sponsor_state": "CA",
                "introduced_date": "2024-01-10",
                "latest_action_date": "2024-02-15",
                "latest_action_text": "Introduced",
                "policy_area": "Veterans",
                "committees_json": "[]",
                "cosponsors_count": 3,
            },
        )

        # Insert oversight event
        execute(
            con,
            """
            INSERT INTO om_events (event_id, event_type, theme, primary_source_type,
                primary_url, pub_timestamp, pub_precision, pub_source,
                title, summary, canonical_refs, fetched_at)
            VALUES (:event_id, :event_type, :theme, :source_type,
                :url, :pub_ts, :precision, :pub_source,
                :title, :summary, :refs, datetime('now'))
        """,
            {
                "event_id": "gao-test-001",
                "event_type": "report",
                "theme": "veterans_health",
                "source_type": "gao",
                "url": "https://www.gao.gov/test",
                "pub_ts": "2026-01-20",
                "precision": "day",
                "pub_source": "gao.gov",
                "title": "GAO-26-100 Veterans Health Report",
                "summary": "Test GAO report about veteran healthcare",
                "refs": '{"gao_report": "GAO-26-100"}',
            },
        )

        # Insert hearing
        execute(
            con,
            """
            INSERT INTO hearings (event_id, congress, chamber, committee_code,
                committee_name, hearing_date, hearing_time, title, meeting_type,
                status, location, url, witnesses_json,
                first_seen_at, updated_at)
            VALUES (:event_id, :congress, :chamber, :committee_code,
                :committee_name, :hearing_date, :hearing_time, :title, :meeting_type,
                :status, :location, :url, :witnesses_json,
                datetime('now'), datetime('now'))
        """,
            {
                "event_id": "hearing-001",
                "congress": 118,
                "chamber": "Senate",
                "committee_code": "SSVA",
                "committee_name": "Senate Veterans Affairs",
                "hearing_date": "2026-01-25",
                "hearing_time": "10:00",
                "title": "VA Oversight Hearing",
                "meeting_type": "hearing",
                "status": "Scheduled",
                "location": "SR-418",
                "url": "https://www.veterans.senate.gov/hearing/test",
                "witnesses_json": '["Witness A", "Witness B"]',
            },
        )

        con.commit()
    finally:
        con.close()
