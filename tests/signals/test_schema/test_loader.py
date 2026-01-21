"""Tests for YAML schema loader."""

import pytest
from src.signals.schema.loader import (
    load_category_schema,
    get_indicator,
    get_trigger,
    get_routing_rule,
    CategorySchema,
)


def test_load_category_schema():
    schema = load_category_schema("oversight_accountability")
    assert schema.category_id == "oversight_accountability"
    assert len(schema.indicators) > 0


def test_get_indicator():
    schema = load_category_schema("oversight_accountability")
    indicator = get_indicator(schema, "gao_oig_reference")
    assert indicator is not None
    assert indicator["indicator_id"] == "gao_oig_reference"


def test_get_trigger():
    schema = load_category_schema("oversight_accountability")
    trigger = get_trigger(schema, "formal_audit_signal")
    assert trigger is not None
    assert trigger["trigger_id"] == "formal_audit_signal"


def test_get_routing_rule():
    schema = load_category_schema("oversight_accountability")
    rule = get_routing_rule(schema, "formal_audit_signal")
    assert rule is not None
    assert rule["severity"] == "high"
    assert "post_slack_alert" in rule["actions"]


def test_schema_validates_evaluators():
    # Should not raise - all evaluators in whitelist
    schema = load_category_schema("oversight_accountability")
    assert schema is not None
