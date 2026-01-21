"""Signals router - routes envelopes through indicators and triggers."""

from dataclasses import dataclass, field
from typing import Optional

from src.signals.envelope import Envelope
from src.signals.schema.loader import load_category_schema, get_routing_rule
from src.signals.engine.evaluator import evaluate_expression, EvaluationResult
from src.signals.suppression import SuppressionManager


@dataclass
class RouteResult:
    """Result of routing an envelope through a trigger."""
    indicator_id: str
    trigger_id: str
    severity: str
    actions: list[str]
    human_review_required: bool
    evaluation: EvaluationResult
    suppressed: bool = False
    suppression_reason: Optional[str] = None


class SignalsRouter:
    """Routes envelopes through signal categories."""

    def __init__(self, categories: list[str]):
        self.schemas = {cat: load_category_schema(cat) for cat in categories}
        self.suppression = SuppressionManager()

    def route(self, envelope: Envelope) -> list[RouteResult]:
        """Route an envelope through all loaded categories."""
        results = []

        for category_id, schema in self.schemas.items():
            for indicator in schema.indicators:
                # Check indicator condition
                if "indicator_condition" in indicator:
                    ind_result = evaluate_expression(
                        indicator["indicator_condition"],
                        envelope,
                        f"{category_id}:indicator_condition",
                    )
                    if not ind_result.passed:
                        continue

                # Evaluate each trigger
                for trigger in indicator.get("triggers", []):
                    trigger_id = trigger["trigger_id"]
                    condition = trigger.get("condition")

                    if not condition:
                        continue

                    eval_result = evaluate_expression(condition, envelope, trigger_id)

                    if eval_result.passed:
                        routing = get_routing_rule(schema, trigger_id)
                        if routing:
                            # Check suppression
                            supp = self.suppression.check_suppression(
                                trigger_id=trigger_id,
                                authority_id=envelope.authority_id,
                                version=envelope.version,
                                cooldown_minutes=routing.get("suppression", {}).get("cooldown_minutes", 60),
                                version_aware=routing.get("suppression", {}).get("version_aware", True),
                            )

                            results.append(RouteResult(
                                indicator_id=indicator["indicator_id"],
                                trigger_id=trigger_id,
                                severity=routing.get("severity", "medium"),
                                actions=routing.get("actions", []),
                                human_review_required=routing.get("human_review_required", False),
                                evaluation=eval_result,
                                suppressed=supp.suppressed,
                                suppression_reason=supp.reason,
                            ))

        return results
