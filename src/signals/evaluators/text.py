"""Text-based evaluators."""

from src.signals.envelope import Envelope, normalize_text
from src.signals.evaluators.base import Evaluator, get_field_value


class ContainsAnyEvaluator(Evaluator):
    """Returns true if field contains any of the specified terms."""

    name = "contains_any"

    def evaluate(self, envelope: Envelope, **args) -> dict:
        field = args.get("field")
        terms = args.get("terms", [])

        # Get field value
        value = get_field_value(envelope, field)
        if value is None:
            return {"passed": False, "evidence": {"matched_terms": []}}

        # Normalize for matching
        normalized_value = normalize_text(str(value))

        # Find matches
        matched_terms = []
        for term in terms:
            normalized_term = normalize_text(term)
            if normalized_term in normalized_value:
                matched_terms.append(term)

        return {
            "passed": len(matched_terms) > 0,
            "evidence": {"matched_terms": matched_terms},
        }
