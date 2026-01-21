"""Comparison evaluators."""

from src.signals.envelope import Envelope
from src.signals.evaluators.base import Evaluator, get_field_value


class EqualsEvaluator(Evaluator):
    """Returns true if field equals the specified value."""

    name = "equals"

    def evaluate(self, envelope: Envelope, **args) -> dict:
        field = args.get("field")
        value = args.get("value")

        actual_value = get_field_value(envelope, field)

        passed = actual_value == value

        return {
            "passed": passed,
            "evidence": {"actual_value": actual_value, "expected_value": value},
        }


class GtEvaluator(Evaluator):
    """Returns true if field > value (numeric comparison)."""

    name = "gt"

    def evaluate(self, envelope: Envelope, **args) -> dict:
        field = args.get("field")
        value = args.get("value")

        actual_value = get_field_value(envelope, field)

        if actual_value is None:
            return {
                "passed": False,
                "evidence": {"actual_value": None, "threshold": value},
            }

        try:
            passed = float(actual_value) > float(value)
        except (TypeError, ValueError):
            passed = False

        return {
            "passed": passed,
            "evidence": {"actual_value": actual_value, "threshold": value},
        }
