"""Evaluator registry."""

from .base import Evaluator, get_field_value, ALLOWED_TOP_LEVEL_FIELDS
from .text import ContainsAnyEvaluator
from .field_match import FieldInEvaluator, FieldIntersectsEvaluator
from .comparison import EqualsEvaluator, GtEvaluator
from .existence import FieldExistsEvaluator, NestedFieldInEvaluator

__all__ = [
    "Evaluator",
    "get_field_value",
    "ALLOWED_TOP_LEVEL_FIELDS",
    "ContainsAnyEvaluator",
    "FieldInEvaluator",
    "FieldIntersectsEvaluator",
    "EqualsEvaluator",
    "GtEvaluator",
    "FieldExistsEvaluator",
    "NestedFieldInEvaluator",
]
