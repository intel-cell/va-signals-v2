"""Evaluator registry with whitelist enforcement."""

from src.signals.evaluators.comparison import EqualsEvaluator, GtEvaluator
from src.signals.evaluators.existence import FieldExistsEvaluator, NestedFieldInEvaluator
from src.signals.evaluators.field_match import FieldInEvaluator, FieldIntersectsEvaluator
from src.signals.evaluators.text import ContainsAnyEvaluator

# Whitelist of allowed evaluators
EVALUATOR_WHITELIST = [
    "contains_any",
    "field_in",
    "field_intersects",
    "equals",
    "gt",
    "field_exists",
    "nested_field_in",
]


class EvaluatorRegistry:
    """Registry of whitelisted evaluators."""

    def __init__(self):
        self._evaluators = {
            "contains_any": ContainsAnyEvaluator(),
            "field_in": FieldInEvaluator(),
            "field_intersects": FieldIntersectsEvaluator(),
            "equals": EqualsEvaluator(),
            "gt": GtEvaluator(),
            "field_exists": FieldExistsEvaluator(),
            "nested_field_in": NestedFieldInEvaluator(),
        }

    def get(self, name: str):
        """Get evaluator by name. Raises if not in whitelist."""
        if name not in EVALUATOR_WHITELIST:
            raise ValueError(f"Evaluator '{name}' not in whitelist")
        return self._evaluators[name]

    def is_allowed(self, name: str) -> bool:
        """Check if evaluator name is in whitelist."""
        return name in EVALUATOR_WHITELIST
