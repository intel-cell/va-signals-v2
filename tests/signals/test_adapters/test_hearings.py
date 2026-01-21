"""Tests for hearings adapter."""

import pytest
from src.signals.adapters.hearings import HearingsAdapter
from src.signals.envelope import Envelope


def test_adapt_hearing_to_envelope():
    adapter = HearingsAdapter()
    hearing = {
        "event_id": "HVAC-2026-01-15-001",
        "congress": 119,
        "chamber": "House",
        "committee_code": "HSVA",
        "committee_name": "House Veterans' Affairs",
        "hearing_date": "2026-01-20",
        "hearing_time": "10:00",
        "title": "Oversight of VA Disability Claims",
        "meeting_type": "hearing",
        "status": "scheduled",
        "location": "Room 334",
        "url": "https://veterans.house.gov/events/...",
        "first_seen_at": "2026-01-15T12:00:00Z",
        "updated_at": "2026-01-15T12:00:00Z",
    }

    envelope = adapter.adapt(hearing)

    assert isinstance(envelope, Envelope)
    assert envelope.event_id == "hearing-HVAC-2026-01-15-001"
    assert envelope.authority_id == "HVAC-2026-01-15-001"
    assert envelope.authority_source == "house_veterans"
    assert envelope.authority_type == "hearing_notice"
    assert envelope.committee == "HVAC"
    assert envelope.metadata["status"] == "scheduled"


def test_adapt_hearing_maps_committee():
    adapter = HearingsAdapter()

    # House VA committee
    hearing = _make_hearing(committee_code="HSVA")
    env = adapter.adapt(hearing)
    assert env.committee == "HVAC"

    # Senate VA committee
    hearing = _make_hearing(committee_code="SSVA")
    env = adapter.adapt(hearing)
    assert env.committee == "SVAC"


def test_adapt_hearing_computes_version():
    adapter = HearingsAdapter()
    hearing = _make_hearing()

    # First version
    env1 = adapter.adapt(hearing, version=1)
    assert env1.version == 1

    # Updated version
    env2 = adapter.adapt(hearing, version=2)
    assert env2.version == 2


def _make_hearing(**overrides):
    base = {
        "event_id": "TEST-001",
        "congress": 119,
        "chamber": "House",
        "committee_code": "HSVA",
        "committee_name": "House Veterans' Affairs",
        "hearing_date": "2026-01-20",
        "title": "Test Hearing",
        "status": "scheduled",
        "first_seen_at": "2026-01-15T12:00:00Z",
        "updated_at": "2026-01-15T12:00:00Z",
    }
    base.update(overrides)
    return base
