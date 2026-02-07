"""Expression tree parser for trigger conditions."""

from dataclasses import dataclass, field

from src.signals.evaluators.registry import EVALUATOR_WHITELIST


@dataclass
class ExpressionNode:
    """Base class for expression nodes."""

    label: str | None = None


@dataclass
class EvaluatorNode(ExpressionNode):
    """Leaf node that calls a registry evaluator."""

    evaluator_name: str = ""
    args: dict = field(default_factory=dict)


@dataclass
class AllOfNode(ExpressionNode):
    """AND - all child expressions must pass."""

    children: list = field(default_factory=list)


@dataclass
class AnyOfNode(ExpressionNode):
    """OR - at least one child expression must pass."""

    children: list = field(default_factory=list)


@dataclass
class NoneOfNode(ExpressionNode):
    """NOT ANY - all child expressions must fail."""

    children: list = field(default_factory=list)


def parse_expression(expr: dict, depth: int = 0) -> ExpressionNode:
    """Parse a condition expression into an expression tree."""
    if "evaluator" in expr:
        return EvaluatorNode(
            evaluator_name=expr["evaluator"],
            args=expr.get("args", {}),
            label=expr.get("label"),
        )

    label = expr.get("label")

    if "all_of" in expr:
        children = [parse_expression(child, depth + 1) for child in expr["all_of"]]
        return AllOfNode(children=children, label=label)

    if "any_of" in expr:
        children = [parse_expression(child, depth + 1) for child in expr["any_of"]]
        return AnyOfNode(children=children, label=label)

    if "none_of" in expr:
        children = [parse_expression(child, depth + 1) for child in expr["none_of"]]
        return NoneOfNode(children=children, label=label)

    raise ValueError(f"Invalid expression node: {expr}")


def validate_expression(expr: dict, max_depth: int = 5, current_depth: int = 0) -> None:
    """Validate an expression against the schema rules."""
    if current_depth > max_depth:
        raise ValueError(f"Expression exceeds max depth of {max_depth}")

    if "evaluator" in expr:
        evaluator_name = expr["evaluator"]
        if evaluator_name not in EVALUATOR_WHITELIST:
            raise ValueError(f"Evaluator '{evaluator_name}' not in whitelist")
        return

    for key in ["all_of", "any_of", "none_of"]:
        if key in expr:
            for child in expr[key]:
                validate_expression(child, max_depth, current_depth + 1)
            return

    raise ValueError(f"Invalid expression structure: {expr}")
