"""Tests for bills adapter."""

import pytest
from src.signals.adapters.bills import BillsAdapter
from src.signals.envelope import Envelope


def test_adapt_bill_to_envelope():
    adapter = BillsAdapter()
    bill = {
        "bill_id": "hr1234-119",
        "congress": 119,
        "bill_type": "HR",
        "bill_number": 1234,
        "title": "Veterans Disability Benefits Improvement Act",
        "sponsor_name": "Rep. Smith",
        "sponsor_party": "D",
        "introduced_date": "2026-01-15",
        "latest_action_date": "2026-01-20",
        "latest_action_text": "Referred to Committee",
        "policy_area": "Armed Forces and National Security",
        "committees_json": '["House Veterans Affairs"]',
        "cosponsors_count": 5,
        "updated_at": "2026-01-20T12:00:00Z",
    }

    envelope = adapter.adapt(bill)

    assert isinstance(envelope, Envelope)
    assert envelope.event_id == "bill-hr1234-119"
    assert envelope.authority_id == "hr1234-119"
    assert envelope.authority_source == "congress_gov"
    assert envelope.authority_type == "bill_text"
    assert "disability_benefits" in envelope.topics


def test_adapt_bill_extracts_topics():
    adapter = BillsAdapter()
    bill = _make_bill(title="VA Claims Backlog Reduction Act", policy_area="Veterans")
    env = adapter.adapt(bill)
    assert "claims_backlog" in env.topics


def test_adapt_bill_maps_committee():
    adapter = BillsAdapter()

    # House VA
    bill = _make_bill(committees_json='["House Veterans Affairs"]')
    env = adapter.adapt(bill)
    assert env.committee == "HVAC"

    # Senate VA
    bill = _make_bill(committees_json='["Senate Veterans Affairs"]')
    env = adapter.adapt(bill)
    assert env.committee == "SVAC"


def test_adapt_bill_computes_version():
    adapter = BillsAdapter()
    bill = _make_bill()

    # First version
    env1 = adapter.adapt(bill, version=1)
    assert env1.version == 1

    # Updated version
    env2 = adapter.adapt(bill, version=2)
    assert env2.version == 2


def test_adapt_bill_builds_body_text():
    adapter = BillsAdapter()
    bill = _make_bill(
        title="Test Bill Title",
        latest_action_text="Passed House",
        policy_area="Veterans Affairs"
    )
    env = adapter.adapt(bill)

    assert "Test Bill Title" in env.body_text
    assert "Latest action: Passed House" in env.body_text
    assert "Policy area: Veterans Affairs" in env.body_text


def test_adapt_bill_builds_source_url():
    adapter = BillsAdapter()
    bill = _make_bill(congress=119, bill_type="HR", bill_number=1234)
    env = adapter.adapt(bill)

    assert env.source_url == "https://congress.gov/bill/119/hr/1234"


def test_adapt_bill_preserves_metadata():
    adapter = BillsAdapter()
    bill = _make_bill(
        congress=119,
        bill_type="HR",
        bill_number=1234,
        sponsor_name="Rep. Smith",
        sponsor_party="D",
        cosponsors_count=10,
        latest_action_date="2026-01-20"
    )
    env = adapter.adapt(bill)

    assert env.metadata["congress"] == 119
    assert env.metadata["bill_type"] == "HR"
    assert env.metadata["bill_number"] == 1234
    assert env.metadata["sponsor_name"] == "Rep. Smith"
    assert env.metadata["sponsor_party"] == "D"
    assert env.metadata["cosponsors_count"] == 10
    assert env.metadata["latest_action_date"] == "2026-01-20"


def test_adapt_bill_extracts_vasrd_topic():
    adapter = BillsAdapter()
    bill = _make_bill(title="VASRD Modernization Act")
    env = adapter.adapt(bill)
    assert "vasrd" in env.topics


def test_adapt_bill_extracts_appeals_topic():
    adapter = BillsAdapter()
    bill = _make_bill(title="BVA Appeals Reform Act")
    env = adapter.adapt(bill)
    assert "appeals" in env.topics


def test_adapt_bill_no_committee_when_none():
    adapter = BillsAdapter()
    bill = _make_bill(committees_json=None)
    env = adapter.adapt(bill)
    assert env.committee is None


def _make_bill(**overrides):
    base = {
        "bill_id": "test-119",
        "congress": 119,
        "bill_type": "HR",
        "bill_number": 1,
        "title": "Test Bill",
        "introduced_date": "2026-01-15",
        "updated_at": "2026-01-15T12:00:00Z",
    }
    base.update(overrides)
    return base
