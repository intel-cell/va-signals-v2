"""Expression tree evaluator."""

from dataclasses import dataclass, field
from typing import Any

from src.signals.engine.parser import (
    AllOfNode,
    AnyOfNode,
    EvaluatorNode,
    NoneOfNode,
    parse_expression,
)
from src.signals.envelope import Envelope
from src.signals.evaluators.registry import EvaluatorRegistry


@dataclass
class EvaluationResult:
    """Result of evaluating an expression tree."""

    passed: bool
    matched_terms: list[str] = field(default_factory=list)
    matched_discriminators: list[str] = field(default_factory=list)
    passed_evaluators: list[str] = field(default_factory=list)
    failed_evaluators: list[str] = field(default_factory=list)
    evidence_map: dict[str, Any] = field(default_factory=dict)


class ExpressionEvaluator:
    """Evaluates expression trees against envelopes."""

    def __init__(self):
        self.registry = EvaluatorRegistry()

    def evaluate(
        self,
        expr: dict,
        envelope: Envelope,
        trigger_id: str,
        path: str = "root",
    ) -> EvaluationResult:
        """Evaluate an expression tree against an envelope."""
        node = parse_expression(expr)
        result = EvaluationResult(passed=False)
        self._evaluate_node(node, envelope, trigger_id, path, result)
        return result

    def _evaluate_node(
        self,
        node,
        envelope: Envelope,
        trigger_id: str,
        path: str,
        result: EvaluationResult,
    ) -> bool:
        """Recursively evaluate a node."""
        if isinstance(node, EvaluatorNode):
            passed = self._evaluate_evaluator(node, envelope, trigger_id, path, result)
            # For top-level evaluator nodes, set the overall result
            if path == "root":
                result.passed = passed
            return passed
        elif isinstance(node, AllOfNode):
            return self._evaluate_all_of(node, envelope, trigger_id, path, result)
        elif isinstance(node, AnyOfNode):
            return self._evaluate_any_of(node, envelope, trigger_id, path, result)
        elif isinstance(node, NoneOfNode):
            return self._evaluate_none_of(node, envelope, trigger_id, path, result)
        return False

    def _evaluate_evaluator(
        self,
        node: EvaluatorNode,
        envelope: Envelope,
        trigger_id: str,
        path: str,
        result: EvaluationResult,
    ) -> bool:
        """Evaluate a single evaluator node."""
        evaluator = self.registry.get(node.evaluator_name)
        eval_result = evaluator.evaluate(envelope, **node.args)

        eval_id = f"{trigger_id}:{path}:{node.evaluator_name}"
        eval_label = f"{node.evaluator_name}({node.args.get('field', '')})"

        result.evidence_map[eval_id] = eval_result

        if eval_result["passed"]:
            result.passed_evaluators.append(eval_label)
            # Collect matched terms
            if "matched_terms" in eval_result.get("evidence", {}):
                result.matched_terms.extend(eval_result["evidence"]["matched_terms"])
            return True
        else:
            result.failed_evaluators.append(eval_label)
            return False

    def _evaluate_all_of(
        self,
        node: AllOfNode,
        envelope: Envelope,
        trigger_id: str,
        path: str,
        result: EvaluationResult,
    ) -> bool:
        """Evaluate all_of node (AND)."""
        for i, child in enumerate(node.children):
            child_path = f"{path}.all_of[{i}]"
            if not self._evaluate_node(child, envelope, trigger_id, child_path, result):
                result.passed = False
                return False
        result.passed = True
        return True

    def _evaluate_any_of(
        self,
        node: AnyOfNode,
        envelope: Envelope,
        trigger_id: str,
        path: str,
        result: EvaluationResult,
    ) -> bool:
        """Evaluate any_of node (OR)."""
        passed_any = False
        for i, child in enumerate(node.children):
            child_path = f"{path}.any_of[{i}]"
            if self._evaluate_node(child, envelope, trigger_id, child_path, result):
                passed_any = True
                # Track matched discriminators if labeled
                if node.label and isinstance(child, EvaluatorNode):
                    disc_label = f"{child.evaluator_name}({child.args.get('field', '')})"
                    result.matched_discriminators.append(disc_label)

        if passed_any:
            result.passed = True
        return passed_any

    def _evaluate_none_of(
        self,
        node: NoneOfNode,
        envelope: Envelope,
        trigger_id: str,
        path: str,
        result: EvaluationResult,
    ) -> bool:
        """Evaluate none_of node (NOT ANY)."""
        for i, child in enumerate(node.children):
            child_path = f"{path}.none_of[{i}]"
            if self._evaluate_node(child, envelope, trigger_id, child_path, result):
                result.passed = False
                return False
        result.passed = True
        return True


# Convenience function
def evaluate_expression(
    expr: dict,
    envelope: Envelope,
    trigger_id: str,
) -> EvaluationResult:
    """Evaluate an expression tree against an envelope."""
    evaluator = ExpressionEvaluator()
    return evaluator.evaluate(expr, envelope, trigger_id)
