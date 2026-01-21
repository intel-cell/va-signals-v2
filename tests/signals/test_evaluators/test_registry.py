"""Tests for evaluator registry."""

import pytest
from src.signals.evaluators.registry import EvaluatorRegistry, EVALUATOR_WHITELIST


def test_registry_contains_all_whitelisted():
    registry = EvaluatorRegistry()
    for name in EVALUATOR_WHITELIST:
        assert registry.get(name) is not None, f"Missing evaluator: {name}"


def test_registry_rejects_unknown():
    registry = EvaluatorRegistry()
    with pytest.raises(ValueError, match="not in whitelist"):
        registry.get("unknown_evaluator")


def test_registry_get_contains_any():
    registry = EvaluatorRegistry()
    evaluator = registry.get("contains_any")
    assert evaluator.name == "contains_any"


def test_registry_get_all_evaluators():
    registry = EvaluatorRegistry()
    evaluators = [
        "contains_any",
        "field_in",
        "field_intersects",
        "equals",
        "gt",
        "field_exists",
        "nested_field_in",
    ]
    for name in evaluators:
        evaluator = registry.get(name)
        assert evaluator.name == name
