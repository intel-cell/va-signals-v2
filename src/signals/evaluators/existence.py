"""Existence and nested field evaluators."""

from src.signals.envelope import Envelope
from src.signals.evaluators.base import Evaluator, get_field_value


class FieldExistsEvaluator(Evaluator):
    """Returns true if field is present and not null."""

    name = "field_exists"

    def evaluate(self, envelope: Envelope, **args) -> dict:
        field = args.get("field")

        actual_value = get_field_value(envelope, field)
        field_present = actual_value is not None

        return {
            "passed": field_present,
            "evidence": {
                "field_present": field_present,
                "field_value_type": type(actual_value).__name__ if actual_value else "NoneType",
            },
        }


class NestedFieldInEvaluator(Evaluator):
    """Access nested field via dot notation and check if value is in list."""

    name = "nested_field_in"

    def evaluate(self, envelope: Envelope, **args) -> dict:
        field = args.get("field")
        values = args.get("values", [])

        # get_field_value handles the metadata.* access policy
        actual_value = get_field_value(envelope, field)

        if actual_value is None:
            return {
                "passed": False,
                "evidence": {"actual_value": None, "matched": False},
            }

        matched = actual_value in values

        return {
            "passed": matched,
            "evidence": {"actual_value": actual_value, "matched": matched},
        }
