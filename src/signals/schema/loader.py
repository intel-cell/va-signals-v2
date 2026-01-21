"""YAML schema loader for signal categories."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from src.signals.engine.parser import validate_expression


@dataclass
class CategorySchema:
    """Loaded category schema."""
    category_id: str
    description: str
    priority: str
    indicators: list[dict]
    routing: list[dict]
    evaluator_whitelist: list[str]
    field_access: dict
    raw: dict = field(default_factory=dict)


def _get_schema_path(category_id: str) -> Path:
    """Get path to schema YAML file."""
    root = Path(__file__).resolve().parents[3]
    return root / "config" / "signals" / f"{category_id}.yaml"


def load_category_schema(category_id: str) -> CategorySchema:
    """Load and validate a category schema from YAML."""
    path = _get_schema_path(category_id)

    if not path.exists():
        raise FileNotFoundError(f"Schema not found: {path}")

    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    # Validate all trigger conditions
    for indicator in raw.get("indicators", []):
        if "indicator_condition" in indicator:
            validate_expression(indicator["indicator_condition"])
        for trigger in indicator.get("triggers", []):
            if "condition" in trigger:
                validate_expression(trigger["condition"])

    return CategorySchema(
        category_id=raw.get("category_id", category_id),
        description=raw.get("description", ""),
        priority=raw.get("priority", "medium"),
        indicators=raw.get("indicators", []),
        routing=raw.get("routing", []),
        evaluator_whitelist=raw.get("evaluator_whitelist", []),
        field_access=raw.get("field_access", {}),
        raw=raw,
    )


def get_indicator(schema: CategorySchema, indicator_id: str) -> Optional[dict]:
    """Get indicator by ID from schema."""
    for indicator in schema.indicators:
        if indicator.get("indicator_id") == indicator_id:
            return indicator
    return None


def get_trigger(schema: CategorySchema, trigger_id: str) -> Optional[dict]:
    """Get trigger by ID from schema."""
    for indicator in schema.indicators:
        for trigger in indicator.get("triggers", []):
            if trigger.get("trigger_id") == trigger_id:
                return trigger
    return None


def get_routing_rule(schema: CategorySchema, trigger_id: str) -> Optional[dict]:
    """Get routing rule for a trigger."""
    for rule in schema.routing:
        if rule.get("trigger_id") == trigger_id:
            return rule
    return None
