"""Tests for expression tree parser."""

import pytest

from src.signals.engine.parser import (
    AllOfNode,
    AnyOfNode,
    EvaluatorNode,
    parse_expression,
    validate_expression,
)


def test_parse_evaluator_node():
    expr = {
        "evaluator": "contains_any",
        "args": {"field": "body_text", "terms": ["GAO", "OIG"]},
    }
    node = parse_expression(expr)
    assert isinstance(node, EvaluatorNode)
    assert node.evaluator_name == "contains_any"
    assert node.args["field"] == "body_text"


def test_parse_all_of_node():
    expr = {
        "all_of": [
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["HVAC"]}},
            {"evaluator": "equals", "args": {"field": "version", "value": 1}},
        ]
    }
    node = parse_expression(expr)
    assert isinstance(node, AllOfNode)
    assert len(node.children) == 2


def test_parse_any_of_with_label():
    expr = {
        "any_of": [
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["HVAC"]}},
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["SVAC"]}},
        ],
        "label": "anti_spam_discriminator",
    }
    node = parse_expression(expr)
    assert isinstance(node, AnyOfNode)
    assert node.label == "anti_spam_discriminator"


def test_parse_nested_expression():
    expr = {
        "all_of": [
            {"evaluator": "contains_any", "args": {"field": "body_text", "terms": ["GAO"]}},
            {
                "any_of": [
                    {"evaluator": "field_in", "args": {"field": "committee", "values": ["HVAC"]}},
                    {
                        "evaluator": "field_intersects",
                        "args": {"field": "topics", "values": ["rating"]},
                    },
                ],
                "label": "discriminator",
            },
        ]
    }
    node = parse_expression(expr)
    assert isinstance(node, AllOfNode)
    assert isinstance(node.children[1], AnyOfNode)
    assert node.children[1].label == "discriminator"


def test_validate_rejects_unknown_evaluator():
    expr = {"evaluator": "unknown_eval", "args": {}}
    with pytest.raises(ValueError, match="not in whitelist"):
        validate_expression(expr)


def test_validate_max_depth():
    # Create deeply nested expression (6 levels)
    expr = {
        "all_of": [
            {
                "all_of": [
                    {
                        "all_of": [
                            {
                                "all_of": [
                                    {
                                        "all_of": [
                                            {
                                                "all_of": [
                                                    {
                                                        "evaluator": "equals",
                                                        "args": {"field": "version", "value": 1},
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    with pytest.raises(ValueError, match="depth"):
        validate_expression(expr, max_depth=5)
