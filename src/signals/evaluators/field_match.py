"""Field matching evaluators."""

from src.signals.envelope import Envelope
from src.signals.evaluators.base import Evaluator, get_field_value


class FieldInEvaluator(Evaluator):
    """Returns true if scalar field value is in the allowed list."""

    name = "field_in"

    def evaluate(self, envelope: Envelope, **args) -> dict:
        field = args.get("field")
        values = args.get("values", [])

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


class FieldIntersectsEvaluator(Evaluator):
    """Returns true if array field contains ANY of the specified values."""

    name = "field_intersects"

    def evaluate(self, envelope: Envelope, **args) -> dict:
        field = args.get("field")
        values = args.get("values", [])

        actual_values = get_field_value(envelope, field)

        if actual_values is None or not isinstance(actual_values, list):
            return {
                "passed": False,
                "evidence": {"actual_values": actual_values, "intersection": []},
            }

        # Find intersection
        intersection = [v for v in values if v in actual_values]

        return {
            "passed": len(intersection) > 0,
            "evidence": {"actual_values": actual_values, "intersection": intersection},
        }
