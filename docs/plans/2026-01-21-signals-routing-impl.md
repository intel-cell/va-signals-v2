# Signals Routing Layer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Signals Routing Layer that classifies authority-validated events and routes them to output channels based on trigger conditions.

**Architecture:** Hybrid YAML + Python evaluator registry. YAML defines what to evaluate (indicators, triggers, routing rules). Python defines how to evaluate (7 whitelisted evaluators). Router never fetches—it receives normalized event envelopes from adapters.

**Tech Stack:** Python 3.11+, SQLite, PyYAML, existing notify_slack.py infrastructure

**Design Document:** `docs/plans/2026-01-21-signals-routing-layer-design.md`

---

## Phase 1: Envelope and Evaluator Registry

### Task 1.1: Normalized Event Envelope

**Files:**
- Create: `src/signals/__init__.py`
- Create: `src/signals/envelope.py`
- Create: `tests/signals/__init__.py`
- Create: `tests/signals/test_envelope.py`

**Step 1: Create package structure**

```bash
mkdir -p src/signals tests/signals
touch src/signals/__init__.py tests/signals/__init__.py
```

**Step 2: Write the failing test**

```python
# tests/signals/test_envelope.py
"""Tests for normalized event envelope."""

import pytest
from src.signals.envelope import Envelope, normalize_text, compute_content_hash


def test_envelope_creation():
    env = Envelope(
        event_id="om-gao-abc123",
        authority_id="GAO-26-106123",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test Hearing",
        body_text="This is the body text.",
    )
    assert env.event_id == "om-gao-abc123"
    assert env.authority_source == "congress_gov"
    assert env.version == 1  # Default


def test_envelope_with_optional_fields():
    env = Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="govinfo",
        authority_type="rule",
        title="Test Rule",
        body_text="Body",
        committee="HVAC",
        topics=["disability_benefits", "rating"],
        metadata={"status": "scheduled"},
    )
    assert env.committee == "HVAC"
    assert env.topics == ["disability_benefits", "rating"]
    assert env.metadata["status"] == "scheduled"


def test_normalize_text():
    # Case insensitive, NFKC, whitespace collapse
    text = "  GAO   Report  "
    normalized = normalize_text(text)
    assert normalized == "gao report"


def test_normalize_text_preserves_punctuation():
    text = "O.I.G. Report"
    normalized = normalize_text(text)
    assert normalized == "o.i.g. report"


def test_compute_content_hash():
    hash1 = compute_content_hash("Title", "Body")
    hash2 = compute_content_hash("Title", "Body")
    hash3 = compute_content_hash("Title", "Different")
    assert hash1 == hash2
    assert hash1 != hash3
    assert hash1.startswith("sha256:")
```

**Step 3: Run test to verify it fails**

```bash
./.venv/bin/python -m pytest tests/signals/test_envelope.py -v
```

Expected: FAIL with "No module named 'src.signals.envelope'"

**Step 4: Write minimal implementation**

```python
# src/signals/envelope.py
"""Normalized event envelope for signals routing."""

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional


def normalize_text(text: str) -> str:
    """Normalize text for matching: lowercase, NFKC, collapse whitespace."""
    if not text:
        return ""
    # NFKC normalization
    text = unicodedata.normalize("NFKC", text)
    # Lowercase
    text = text.lower()
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_content_hash(title: str, body_text: str) -> str:
    """Compute SHA256 hash of normalized content."""
    normalized = normalize_text(f"{title} {body_text}")
    hash_bytes = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{hash_bytes}"


@dataclass
class Envelope:
    """Normalized event envelope consumed by the signals router."""

    # Identity
    event_id: str
    authority_id: str

    # Authority
    authority_source: str  # govinfo | congress_gov | house_veterans | senate_veterans
    authority_type: str  # hearing_notice | bill_text | rule | report | press_release

    # Content
    title: str
    body_text: str

    # Classification hints (optional)
    committee: Optional[str] = None  # HVAC | SVAC | null
    subcommittee: Optional[str] = None
    topics: list[str] = field(default_factory=list)

    # Change detection
    content_hash: Optional[str] = None
    version: int = 1

    # Temporal
    published_at: Optional[str] = None
    published_at_source: str = "derived"  # authority | derived
    event_start_at: Optional[str] = None

    # Provenance
    source_url: Optional[str] = None
    fetched_at: Optional[str] = None

    # Structured metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Compute content_hash if not provided."""
        if self.content_hash is None:
            self.content_hash = compute_content_hash(self.title, self.body_text)
```

**Step 5: Run test to verify it passes**

```bash
./.venv/bin/python -m pytest tests/signals/test_envelope.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add src/signals/ tests/signals/
git commit -m "feat(signals): add normalized event envelope"
```

---

### Task 1.2: Evaluator Base Class and contains_any

**Files:**
- Create: `src/signals/evaluators/__init__.py`
- Create: `src/signals/evaluators/base.py`
- Create: `src/signals/evaluators/text.py`
- Create: `tests/signals/test_evaluators/__init__.py`
- Create: `tests/signals/test_evaluators/test_text.py`

**Step 1: Write the failing test**

```python
# tests/signals/test_evaluators/test_text.py
"""Tests for text evaluators."""

import pytest
from src.signals.envelope import Envelope
from src.signals.evaluators.text import ContainsAnyEvaluator


@pytest.fixture
def sample_envelope():
    return Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="VA Hearing on GAO Report",
        body_text="The GAO found issues with OIG oversight of disability claims.",
    )


def test_contains_any_matches(sample_envelope):
    evaluator = ContainsAnyEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="body_text",
        terms=["GAO", "OIG", "audit"],
    )
    assert result["passed"] is True
    assert "GAO" in result["evidence"]["matched_terms"]
    assert "OIG" in result["evidence"]["matched_terms"]


def test_contains_any_no_match(sample_envelope):
    evaluator = ContainsAnyEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="body_text",
        terms=["VASRD", "modernization"],
    )
    assert result["passed"] is False
    assert result["evidence"]["matched_terms"] == []


def test_contains_any_case_insensitive(sample_envelope):
    evaluator = ContainsAnyEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="body_text",
        terms=["gao", "oig"],  # lowercase
    )
    assert result["passed"] is True
    assert len(result["evidence"]["matched_terms"]) == 2


def test_contains_any_title_field(sample_envelope):
    evaluator = ContainsAnyEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="title",
        terms=["GAO Report"],
    )
    assert result["passed"] is True


def test_contains_any_invalid_field(sample_envelope):
    evaluator = ContainsAnyEvaluator()
    with pytest.raises(ValueError, match="not in allowed fields"):
        evaluator.evaluate(
            sample_envelope,
            field="invalid_field",
            terms=["test"],
        )
```

**Step 2: Run test to verify it fails**

```bash
./.venv/bin/python -m pytest tests/signals/test_evaluators/test_text.py -v
```

Expected: FAIL

**Step 3: Write minimal implementation**

```python
# src/signals/evaluators/base.py
"""Base class for evaluators."""

from abc import ABC, abstractmethod
from typing import Any

from src.signals.envelope import Envelope


# Field access policy
ALLOWED_TOP_LEVEL_FIELDS = {
    "event_id", "authority_id", "authority_source", "authority_type",
    "committee", "subcommittee", "topics", "title", "body_text",
    "content_hash", "version", "published_at", "published_at_source",
    "event_start_at", "source_url", "fetched_at",
}
ALLOWED_NESTED_PREFIX = "metadata."


def get_field_value(envelope: Envelope, field: str) -> Any:
    """Get field value from envelope, respecting access policy."""
    if field in ALLOWED_TOP_LEVEL_FIELDS:
        return getattr(envelope, field, None)
    elif field.startswith(ALLOWED_NESTED_PREFIX):
        # Nested field access: metadata.status -> envelope.metadata["status"]
        parts = field.split(".", 1)
        if len(parts) == 2 and parts[0] == "metadata":
            return envelope.metadata.get(parts[1])
    raise ValueError(f"Field '{field}' not in allowed fields")


class Evaluator(ABC):
    """Base class for all evaluators."""

    name: str = "base"

    @abstractmethod
    def evaluate(self, envelope: Envelope, **args) -> dict:
        """
        Evaluate the envelope against the condition.

        Returns:
            {
                "passed": bool,
                "evidence": { ... evaluator-specific evidence ... }
            }
        """
        pass
```

```python
# src/signals/evaluators/text.py
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
```

```python
# src/signals/evaluators/__init__.py
"""Evaluator registry."""

from .base import Evaluator, get_field_value, ALLOWED_TOP_LEVEL_FIELDS
from .text import ContainsAnyEvaluator

__all__ = [
    "Evaluator",
    "get_field_value",
    "ALLOWED_TOP_LEVEL_FIELDS",
    "ContainsAnyEvaluator",
]
```

**Step 4: Run test to verify it passes**

```bash
./.venv/bin/python -m pytest tests/signals/test_evaluators/test_text.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/signals/evaluators/ tests/signals/test_evaluators/
git commit -m "feat(signals): add contains_any evaluator with field access policy"
```

---

### Task 1.3: field_in and field_intersects Evaluators

**Files:**
- Create: `src/signals/evaluators/field_match.py`
- Create: `tests/signals/test_evaluators/test_field_match.py`

**Step 1: Write the failing test**

```python
# tests/signals/test_evaluators/test_field_match.py
"""Tests for field match evaluators."""

import pytest
from src.signals.envelope import Envelope
from src.signals.evaluators.field_match import FieldInEvaluator, FieldIntersectsEvaluator


@pytest.fixture
def sample_envelope():
    return Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test",
        body_text="Body",
        committee="HVAC",
        topics=["disability_benefits", "exam_quality"],
    )


# FieldInEvaluator tests
def test_field_in_matches(sample_envelope):
    evaluator = FieldInEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="committee",
        values=["HVAC", "SVAC"],
    )
    assert result["passed"] is True
    assert result["evidence"]["actual_value"] == "HVAC"
    assert result["evidence"]["matched"] is True


def test_field_in_no_match(sample_envelope):
    evaluator = FieldInEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="committee",
        values=["HASC", "SASC"],
    )
    assert result["passed"] is False
    assert result["evidence"]["matched"] is False


def test_field_in_null_value():
    env = Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test",
        body_text="Body",
        committee=None,
    )
    evaluator = FieldInEvaluator()
    result = evaluator.evaluate(env, field="committee", values=["HVAC"])
    assert result["passed"] is False


# FieldIntersectsEvaluator tests
def test_field_intersects_matches(sample_envelope):
    evaluator = FieldIntersectsEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="topics",
        values=["disability_benefits", "rating"],
    )
    assert result["passed"] is True
    assert "disability_benefits" in result["evidence"]["intersection"]


def test_field_intersects_no_match(sample_envelope):
    evaluator = FieldIntersectsEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="topics",
        values=["vasrd", "appeals"],
    )
    assert result["passed"] is False
    assert result["evidence"]["intersection"] == []


def test_field_intersects_empty_field():
    env = Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test",
        body_text="Body",
        topics=[],
    )
    evaluator = FieldIntersectsEvaluator()
    result = evaluator.evaluate(env, field="topics", values=["rating"])
    assert result["passed"] is False
```

**Step 2: Run test to verify it fails**

```bash
./.venv/bin/python -m pytest tests/signals/test_evaluators/test_field_match.py -v
```

**Step 3: Write minimal implementation**

```python
# src/signals/evaluators/field_match.py
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
```

**Step 4: Update `__init__.py`**

```python
# src/signals/evaluators/__init__.py
"""Evaluator registry."""

from .base import Evaluator, get_field_value, ALLOWED_TOP_LEVEL_FIELDS
from .text import ContainsAnyEvaluator
from .field_match import FieldInEvaluator, FieldIntersectsEvaluator

__all__ = [
    "Evaluator",
    "get_field_value",
    "ALLOWED_TOP_LEVEL_FIELDS",
    "ContainsAnyEvaluator",
    "FieldInEvaluator",
    "FieldIntersectsEvaluator",
]
```

**Step 5: Run test to verify it passes**

```bash
./.venv/bin/python -m pytest tests/signals/test_evaluators/test_field_match.py -v
```

**Step 6: Commit**

```bash
git add src/signals/evaluators/ tests/signals/test_evaluators/
git commit -m "feat(signals): add field_in and field_intersects evaluators"
```

---

### Task 1.4: equals and gt Evaluators

**Files:**
- Create: `src/signals/evaluators/comparison.py`
- Create: `tests/signals/test_evaluators/test_comparison.py`

**Step 1: Write the failing test**

```python
# tests/signals/test_evaluators/test_comparison.py
"""Tests for comparison evaluators."""

import pytest
from src.signals.envelope import Envelope
from src.signals.evaluators.comparison import EqualsEvaluator, GtEvaluator


@pytest.fixture
def sample_envelope():
    return Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test",
        body_text="Body",
        version=2,
    )


# EqualsEvaluator tests
def test_equals_matches(sample_envelope):
    evaluator = EqualsEvaluator()
    result = evaluator.evaluate(sample_envelope, field="version", value=2)
    assert result["passed"] is True
    assert result["evidence"]["actual_value"] == 2
    assert result["evidence"]["expected_value"] == 2


def test_equals_no_match(sample_envelope):
    evaluator = EqualsEvaluator()
    result = evaluator.evaluate(sample_envelope, field="version", value=1)
    assert result["passed"] is False


def test_equals_string_match(sample_envelope):
    evaluator = EqualsEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="authority_type",
        value="hearing_notice",
    )
    assert result["passed"] is True


# GtEvaluator tests
def test_gt_passes(sample_envelope):
    evaluator = GtEvaluator()
    result = evaluator.evaluate(sample_envelope, field="version", value=1)
    assert result["passed"] is True
    assert result["evidence"]["actual_value"] == 2
    assert result["evidence"]["threshold"] == 1


def test_gt_fails_equal(sample_envelope):
    evaluator = GtEvaluator()
    result = evaluator.evaluate(sample_envelope, field="version", value=2)
    assert result["passed"] is False


def test_gt_fails_less(sample_envelope):
    evaluator = GtEvaluator()
    result = evaluator.evaluate(sample_envelope, field="version", value=3)
    assert result["passed"] is False


def test_gt_null_field():
    env = Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test",
        body_text="Body",
    )
    evaluator = GtEvaluator()
    # version defaults to 1
    result = evaluator.evaluate(env, field="version", value=0)
    assert result["passed"] is True
```

**Step 2: Run test to verify it fails**

```bash
./.venv/bin/python -m pytest tests/signals/test_evaluators/test_comparison.py -v
```

**Step 3: Write minimal implementation**

```python
# src/signals/evaluators/comparison.py
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
```

**Step 4: Update `__init__.py`**

Add to `src/signals/evaluators/__init__.py`:

```python
from .comparison import EqualsEvaluator, GtEvaluator
```

**Step 5: Run test to verify it passes**

```bash
./.venv/bin/python -m pytest tests/signals/test_evaluators/test_comparison.py -v
```

**Step 6: Commit**

```bash
git add src/signals/evaluators/ tests/signals/test_evaluators/
git commit -m "feat(signals): add equals and gt evaluators"
```

---

### Task 1.5: field_exists and nested_field_in Evaluators

**Files:**
- Create: `src/signals/evaluators/existence.py`
- Create: `tests/signals/test_evaluators/test_existence.py`

**Step 1: Write the failing test**

```python
# tests/signals/test_evaluators/test_existence.py
"""Tests for existence and nested field evaluators."""

import pytest
from src.signals.envelope import Envelope
from src.signals.evaluators.existence import FieldExistsEvaluator, NestedFieldInEvaluator


@pytest.fixture
def sample_envelope():
    return Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test",
        body_text="Body",
        committee="HVAC",
        metadata={"status": "cancelled", "priority": "high"},
    )


# FieldExistsEvaluator tests
def test_field_exists_true(sample_envelope):
    evaluator = FieldExistsEvaluator()
    result = evaluator.evaluate(sample_envelope, field="committee")
    assert result["passed"] is True
    assert result["evidence"]["field_present"] is True


def test_field_exists_false():
    env = Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Test",
        body_text="Body",
        committee=None,
    )
    evaluator = FieldExistsEvaluator()
    result = evaluator.evaluate(env, field="committee")
    assert result["passed"] is False
    assert result["evidence"]["field_present"] is False


# NestedFieldInEvaluator tests
def test_nested_field_in_matches(sample_envelope):
    evaluator = NestedFieldInEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="metadata.status",
        values=["cancelled", "rescheduled", "postponed"],
    )
    assert result["passed"] is True
    assert result["evidence"]["actual_value"] == "cancelled"
    assert result["evidence"]["matched"] is True


def test_nested_field_in_no_match(sample_envelope):
    evaluator = NestedFieldInEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="metadata.status",
        values=["scheduled"],
    )
    assert result["passed"] is False


def test_nested_field_in_missing_key(sample_envelope):
    evaluator = NestedFieldInEvaluator()
    result = evaluator.evaluate(
        sample_envelope,
        field="metadata.nonexistent",
        values=["value"],
    )
    assert result["passed"] is False
    assert result["evidence"]["actual_value"] is None


def test_nested_field_in_invalid_prefix(sample_envelope):
    evaluator = NestedFieldInEvaluator()
    with pytest.raises(ValueError, match="not in allowed fields"):
        evaluator.evaluate(
            sample_envelope,
            field="invalid.field",
            values=["value"],
        )
```

**Step 2: Run test to verify it fails**

```bash
./.venv/bin/python -m pytest tests/signals/test_evaluators/test_existence.py -v
```

**Step 3: Write minimal implementation**

```python
# src/signals/evaluators/existence.py
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
```

**Step 4: Update `__init__.py`**

Add to `src/signals/evaluators/__init__.py`:

```python
from .existence import FieldExistsEvaluator, NestedFieldInEvaluator
```

**Step 5: Run test to verify it passes**

```bash
./.venv/bin/python -m pytest tests/signals/test_evaluators/test_existence.py -v
```

**Step 6: Commit**

```bash
git add src/signals/evaluators/ tests/signals/test_evaluators/
git commit -m "feat(signals): add field_exists and nested_field_in evaluators"
```

---

### Task 1.6: Evaluator Registry

**Files:**
- Create: `src/signals/evaluators/registry.py`
- Create: `tests/signals/test_evaluators/test_registry.py`

**Step 1: Write the failing test**

```python
# tests/signals/test_evaluators/test_registry.py
"""Tests for evaluator registry."""

import pytest
from src.signals.evaluators.registry import EvaluatorRegistry, EVALUATOR_WHITELIST


def test_registry_contains_all_whitelisted():
    registry = EvaluatorRegistry()
    for name in EVALUATOR_WHITELIST:
        assert registry.get(name) is not None, f"Missing evaluator: {name}"


def test_registry_rejects_unknown():
    registry = EvaluatorRegistry()
    with pytest.raises(ValueError, match="not in whitelist"):
        registry.get("unknown_evaluator")


def test_registry_get_contains_any():
    registry = EvaluatorRegistry()
    evaluator = registry.get("contains_any")
    assert evaluator.name == "contains_any"


def test_registry_get_all_evaluators():
    registry = EvaluatorRegistry()
    evaluators = [
        "contains_any",
        "field_in",
        "field_intersects",
        "equals",
        "gt",
        "field_exists",
        "nested_field_in",
    ]
    for name in evaluators:
        evaluator = registry.get(name)
        assert evaluator.name == name
```

**Step 2: Run test to verify it fails**

```bash
./.venv/bin/python -m pytest tests/signals/test_evaluators/test_registry.py -v
```

**Step 3: Write minimal implementation**

```python
# src/signals/evaluators/registry.py
"""Evaluator registry with whitelist enforcement."""

from src.signals.evaluators.text import ContainsAnyEvaluator
from src.signals.evaluators.field_match import FieldInEvaluator, FieldIntersectsEvaluator
from src.signals.evaluators.comparison import EqualsEvaluator, GtEvaluator
from src.signals.evaluators.existence import FieldExistsEvaluator, NestedFieldInEvaluator


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
```

**Step 4: Update `__init__.py`**

```python
# src/signals/evaluators/__init__.py
"""Evaluator registry."""

from .base import Evaluator, get_field_value, ALLOWED_TOP_LEVEL_FIELDS
from .text import ContainsAnyEvaluator
from .field_match import FieldInEvaluator, FieldIntersectsEvaluator
from .comparison import EqualsEvaluator, GtEvaluator
from .existence import FieldExistsEvaluator, NestedFieldInEvaluator
from .registry import EvaluatorRegistry, EVALUATOR_WHITELIST

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
    "EvaluatorRegistry",
    "EVALUATOR_WHITELIST",
]
```

**Step 5: Run test to verify it passes**

```bash
./.venv/bin/python -m pytest tests/signals/test_evaluators/test_registry.py -v
```

**Step 6: Commit**

```bash
git add src/signals/evaluators/ tests/signals/test_evaluators/
git commit -m "feat(signals): add evaluator registry with whitelist"
```

---

## Phase 2: Expression Engine

### Task 2.1: Expression Tree Parser

**Files:**
- Create: `src/signals/engine/__init__.py`
- Create: `src/signals/engine/parser.py`
- Create: `tests/signals/test_engine/__init__.py`
- Create: `tests/signals/test_engine/test_parser.py`

**Step 1: Write the failing test**

```python
# tests/signals/test_engine/test_parser.py
"""Tests for expression tree parser."""

import pytest
from src.signals.engine.parser import (
    parse_expression,
    validate_expression,
    ExpressionNode,
    EvaluatorNode,
    AllOfNode,
    AnyOfNode,
    NoneOfNode,
)


def test_parse_evaluator_node():
    expr = {
        "evaluator": "contains_any",
        "args": {"field": "body_text", "terms": ["GAO", "OIG"]},
    }
    node = parse_expression(expr)
    assert isinstance(node, EvaluatorNode)
    assert node.evaluator_name == "contains_any"
    assert node.args["field"] == "body_text"


def test_parse_all_of_node():
    expr = {
        "all_of": [
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["HVAC"]}},
            {"evaluator": "equals", "args": {"field": "version", "value": 1}},
        ]
    }
    node = parse_expression(expr)
    assert isinstance(node, AllOfNode)
    assert len(node.children) == 2


def test_parse_any_of_with_label():
    expr = {
        "any_of": [
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["HVAC"]}},
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["SVAC"]}},
        ],
        "label": "anti_spam_discriminator",
    }
    node = parse_expression(expr)
    assert isinstance(node, AnyOfNode)
    assert node.label == "anti_spam_discriminator"


def test_parse_nested_expression():
    expr = {
        "all_of": [
            {"evaluator": "contains_any", "args": {"field": "body_text", "terms": ["GAO"]}},
            {
                "any_of": [
                    {"evaluator": "field_in", "args": {"field": "committee", "values": ["HVAC"]}},
                    {"evaluator": "field_intersects", "args": {"field": "topics", "values": ["rating"]}},
                ],
                "label": "discriminator",
            },
        ]
    }
    node = parse_expression(expr)
    assert isinstance(node, AllOfNode)
    assert isinstance(node.children[1], AnyOfNode)
    assert node.children[1].label == "discriminator"


def test_validate_rejects_unknown_evaluator():
    expr = {"evaluator": "unknown_eval", "args": {}}
    with pytest.raises(ValueError, match="not in whitelist"):
        validate_expression(expr)


def test_validate_max_depth():
    # Create deeply nested expression (6 levels)
    expr = {"all_of": [{"all_of": [{"all_of": [{"all_of": [{"all_of": [{"all_of": [
        {"evaluator": "equals", "args": {"field": "version", "value": 1}}
    ]}]}]}]}]}]}
    with pytest.raises(ValueError, match="depth"):
        validate_expression(expr, max_depth=5)
```

**Step 2: Run test to verify it fails**

```bash
./.venv/bin/python -m pytest tests/signals/test_engine/test_parser.py -v
```

**Step 3: Write minimal implementation**

```python
# src/signals/engine/parser.py
"""Expression tree parser for trigger conditions."""

from dataclasses import dataclass, field
from typing import Any, Optional, Union

from src.signals.evaluators.registry import EVALUATOR_WHITELIST


@dataclass
class ExpressionNode:
    """Base class for expression nodes."""
    label: Optional[str] = None


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
```

```python
# src/signals/engine/__init__.py
"""Signals evaluation engine."""

from .parser import (
    parse_expression,
    validate_expression,
    ExpressionNode,
    EvaluatorNode,
    AllOfNode,
    AnyOfNode,
    NoneOfNode,
)

__all__ = [
    "parse_expression",
    "validate_expression",
    "ExpressionNode",
    "EvaluatorNode",
    "AllOfNode",
    "AnyOfNode",
    "NoneOfNode",
]
```

**Step 4: Run test to verify it passes**

```bash
./.venv/bin/python -m pytest tests/signals/test_engine/test_parser.py -v
```

**Step 5: Commit**

```bash
git add src/signals/engine/ tests/signals/test_engine/
git commit -m "feat(signals): add expression tree parser with validation"
```

---

### Task 2.2: Expression Evaluator

**Files:**
- Create: `src/signals/engine/evaluator.py`
- Create: `tests/signals/test_engine/test_evaluator.py`

**Step 1: Write the failing test**

```python
# tests/signals/test_engine/test_evaluator.py
"""Tests for expression evaluator."""

import pytest
from src.signals.envelope import Envelope
from src.signals.engine.evaluator import evaluate_expression, EvaluationResult


@pytest.fixture
def gao_envelope():
    return Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Hearing on GAO Report",
        body_text="The GAO found issues with VA disability claims processing.",
        committee="HVAC",
        topics=["disability_benefits", "claims_backlog"],
        version=1,
    )


def test_evaluate_simple_evaluator(gao_envelope):
    expr = {
        "evaluator": "contains_any",
        "args": {"field": "body_text", "terms": ["GAO", "OIG"]},
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is True
    assert "GAO" in result.matched_terms


def test_evaluate_all_of_passes(gao_envelope):
    expr = {
        "all_of": [
            {"evaluator": "contains_any", "args": {"field": "body_text", "terms": ["GAO"]}},
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["HVAC", "SVAC"]}},
        ]
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is True


def test_evaluate_all_of_fails(gao_envelope):
    expr = {
        "all_of": [
            {"evaluator": "contains_any", "args": {"field": "body_text", "terms": ["GAO"]}},
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["SASC"]}},
        ]
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is False


def test_evaluate_any_of_passes(gao_envelope):
    expr = {
        "any_of": [
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["SASC"]}},
            {"evaluator": "field_in", "args": {"field": "committee", "values": ["HVAC"]}},
        ],
        "label": "discriminator",
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is True
    assert "field_in(committee)" in result.matched_discriminators


def test_evaluate_collects_evidence(gao_envelope):
    expr = {
        "all_of": [
            {"evaluator": "contains_any", "args": {"field": "body_text", "terms": ["GAO", "OIG"]}},
            {
                "any_of": [
                    {"evaluator": "field_in", "args": {"field": "committee", "values": ["HVAC"]}},
                ],
                "label": "anti_spam_discriminator",
            },
        ]
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is True
    assert len(result.passed_evaluators) >= 2
    assert len(result.evidence_map) >= 2


def test_evaluate_tracks_failed_evaluators(gao_envelope):
    expr = {
        "all_of": [
            {"evaluator": "contains_any", "args": {"field": "body_text", "terms": ["VASRD"]}},
        ]
    }
    result = evaluate_expression(expr, gao_envelope, "test_trigger")
    assert result.passed is False
    assert len(result.failed_evaluators) > 0
```

**Step 2: Run test to verify it fails**

```bash
./.venv/bin/python -m pytest tests/signals/test_engine/test_evaluator.py -v
```

**Step 3: Write minimal implementation**

```python
# src/signals/engine/evaluator.py
"""Expression tree evaluator."""

from dataclasses import dataclass, field
from typing import Any

from src.signals.envelope import Envelope
from src.signals.evaluators.registry import EvaluatorRegistry
from src.signals.engine.parser import (
    parse_expression,
    EvaluatorNode,
    AllOfNode,
    AnyOfNode,
    NoneOfNode,
)


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
            return self._evaluate_evaluator(node, envelope, trigger_id, path, result)
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
```

**Step 4: Update engine `__init__.py`**

```python
# src/signals/engine/__init__.py
"""Signals evaluation engine."""

from .parser import (
    parse_expression,
    validate_expression,
    ExpressionNode,
    EvaluatorNode,
    AllOfNode,
    AnyOfNode,
    NoneOfNode,
)
from .evaluator import evaluate_expression, EvaluationResult, ExpressionEvaluator

__all__ = [
    "parse_expression",
    "validate_expression",
    "ExpressionNode",
    "EvaluatorNode",
    "AllOfNode",
    "AnyOfNode",
    "NoneOfNode",
    "evaluate_expression",
    "EvaluationResult",
    "ExpressionEvaluator",
]
```

**Step 5: Run test to verify it passes**

```bash
./.venv/bin/python -m pytest tests/signals/test_engine/test_evaluator.py -v
```

**Step 6: Commit**

```bash
git add src/signals/engine/ tests/signals/test_engine/
git commit -m "feat(signals): add expression tree evaluator with evidence collection"
```

---

## Phase 3: Schema Loader and Suppression

### Task 3.1: YAML Schema Loader

**Files:**
- Create: `src/signals/schema/__init__.py`
- Create: `src/signals/schema/loader.py`
- Create: `config/signals/oversight_accountability.yaml`
- Create: `tests/signals/test_schema/__init__.py`
- Create: `tests/signals/test_schema/test_loader.py`

**Step 1: Write the failing test**

```python
# tests/signals/test_schema/test_loader.py
"""Tests for YAML schema loader."""

import pytest
from src.signals.schema.loader import (
    load_category_schema,
    get_indicator,
    get_trigger,
    get_routing_rule,
    CategorySchema,
)


def test_load_category_schema():
    schema = load_category_schema("oversight_accountability")
    assert schema.category_id == "oversight_accountability"
    assert len(schema.indicators) > 0


def test_get_indicator():
    schema = load_category_schema("oversight_accountability")
    indicator = get_indicator(schema, "gao_oig_reference")
    assert indicator is not None
    assert indicator["indicator_id"] == "gao_oig_reference"


def test_get_trigger():
    schema = load_category_schema("oversight_accountability")
    trigger = get_trigger(schema, "formal_audit_signal")
    assert trigger is not None
    assert trigger["trigger_id"] == "formal_audit_signal"


def test_get_routing_rule():
    schema = load_category_schema("oversight_accountability")
    rule = get_routing_rule(schema, "formal_audit_signal")
    assert rule is not None
    assert rule["severity"] == "high"
    assert "post_slack_alert" in rule["actions"]


def test_schema_validates_evaluators():
    # Should not raise - all evaluators in whitelist
    schema = load_category_schema("oversight_accountability")
    assert schema is not None
```

**Step 2: Run test to verify it fails**

```bash
./.venv/bin/python -m pytest tests/signals/test_schema/test_loader.py -v
```

**Step 3: Create the YAML schema file**

Copy the Oversight/Accountability YAML from the design document to:
`config/signals/oversight_accountability.yaml`

(This is the full YAML from the design doc - too long to include inline, but it's the complete schema with indicators, triggers, and routing rules)

**Step 4: Write minimal implementation**

```python
# src/signals/schema/loader.py
"""YAML schema loader for signal categories."""

import os
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
```

```python
# src/signals/schema/__init__.py
"""Schema loading and validation."""

from .loader import (
    load_category_schema,
    get_indicator,
    get_trigger,
    get_routing_rule,
    CategorySchema,
)

__all__ = [
    "load_category_schema",
    "get_indicator",
    "get_trigger",
    "get_routing_rule",
    "CategorySchema",
]
```

**Step 5: Run test to verify it passes**

```bash
./.venv/bin/python -m pytest tests/signals/test_schema/test_loader.py -v
```

**Step 6: Commit**

```bash
git add src/signals/schema/ config/signals/ tests/signals/test_schema/
git commit -m "feat(signals): add YAML schema loader with validation"
```

---

### Task 3.2: Suppression Manager

**Files:**
- Modify: `schema.sql` (add suppression table)
- Create: `src/signals/suppression.py`
- Create: `tests/signals/test_suppression.py`

**Step 1: Add schema**

Add to `schema.sql`:

```sql
-- Signals routing suppression state
CREATE TABLE IF NOT EXISTS signal_suppression (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key TEXT UNIQUE NOT NULL,
    trigger_id TEXT NOT NULL,
    authority_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    last_fired_at TEXT NOT NULL,
    cooldown_until TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signal_suppression_dedupe ON signal_suppression(dedupe_key);
CREATE INDEX IF NOT EXISTS idx_signal_suppression_cooldown ON signal_suppression(cooldown_until);
```

**Step 2: Write the failing test**

```python
# tests/signals/test_suppression.py
"""Tests for suppression manager."""

import pytest
from datetime import datetime, timezone, timedelta
from src.signals.suppression import SuppressionManager, SuppressionResult


@pytest.fixture
def manager(tmp_path, monkeypatch):
    """Create suppression manager with test DB."""
    import src.db as db_module
    test_db = tmp_path / "test_signals.db"
    monkeypatch.setattr(db_module, "DB_PATH", test_db)
    db_module.init_db()
    return SuppressionManager()


def test_first_fire_not_suppressed(manager):
    result = manager.check_suppression(
        trigger_id="formal_audit_signal",
        authority_id="GAO-26-123",
        version=1,
        cooldown_minutes=60,
        version_aware=True,
    )
    assert result.suppressed is False
    assert result.reason is None


def test_second_fire_within_cooldown_suppressed(manager):
    # First fire
    manager.check_suppression("t1", "auth-1", 1, 60, True)
    manager.record_fire("t1", "auth-1", 1, 60)

    # Second fire within cooldown
    result = manager.check_suppression("t1", "auth-1", 1, 60, True)
    assert result.suppressed is True
    assert result.reason == "cooldown"


def test_version_bump_bypasses_cooldown(manager):
    # First fire
    manager.check_suppression("t1", "auth-1", 1, 60, True)
    manager.record_fire("t1", "auth-1", 1, 60)

    # Second fire with version bump
    result = manager.check_suppression("t1", "auth-1", 2, 60, True)
    assert result.suppressed is False


def test_expired_cooldown_not_suppressed(manager):
    # First fire
    manager.check_suppression("t1", "auth-1", 1, 0, True)  # 0 minute cooldown
    manager.record_fire("t1", "auth-1", 1, 0)

    # Second fire after cooldown expired
    result = manager.check_suppression("t1", "auth-1", 1, 0, True)
    assert result.suppressed is False


def test_dedupe_key_composition(manager):
    key = manager._make_dedupe_key("trigger_1", "auth_123")
    assert "trigger_1" in key
    assert "auth_123" in key
```

**Step 3: Write minimal implementation**

```python
# src/signals/suppression.py
"""Suppression manager for signal triggers."""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.db import connect


@dataclass
class SuppressionResult:
    """Result of suppression check."""
    suppressed: bool
    reason: Optional[str] = None  # "cooldown" | "dedupe" | None


class SuppressionManager:
    """Manages trigger suppression state."""

    def _make_dedupe_key(self, trigger_id: str, authority_id: str) -> str:
        """Create composite dedupe key."""
        return f"{trigger_id}:{authority_id}"

    def check_suppression(
        self,
        trigger_id: str,
        authority_id: str,
        version: int,
        cooldown_minutes: int,
        version_aware: bool,
    ) -> SuppressionResult:
        """Check if a trigger fire should be suppressed."""
        dedupe_key = self._make_dedupe_key(trigger_id, authority_id)
        now = datetime.now(timezone.utc)

        con = connect()
        cur = con.cursor()
        cur.execute(
            "SELECT version, cooldown_until FROM signal_suppression WHERE dedupe_key = ?",
            (dedupe_key,),
        )
        row = cur.fetchone()
        con.close()

        if row is None:
            return SuppressionResult(suppressed=False)

        stored_version, cooldown_until_str = row
        cooldown_until = datetime.fromisoformat(cooldown_until_str.replace("Z", "+00:00"))

        # Version bump bypasses cooldown if version_aware
        if version_aware and version > stored_version:
            return SuppressionResult(suppressed=False)

        # Check cooldown
        if now < cooldown_until:
            return SuppressionResult(suppressed=True, reason="cooldown")

        return SuppressionResult(suppressed=False)

    def record_fire(
        self,
        trigger_id: str,
        authority_id: str,
        version: int,
        cooldown_minutes: int,
    ) -> None:
        """Record a trigger fire for suppression tracking."""
        dedupe_key = self._make_dedupe_key(trigger_id, authority_id)
        now = datetime.now(timezone.utc)
        cooldown_until = now + timedelta(minutes=cooldown_minutes)

        con = connect()
        con.execute(
            """
            INSERT INTO signal_suppression (dedupe_key, trigger_id, authority_id, version, last_fired_at, cooldown_until)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(dedupe_key) DO UPDATE SET
                version = excluded.version,
                last_fired_at = excluded.last_fired_at,
                cooldown_until = excluded.cooldown_until
            """,
            (
                dedupe_key,
                trigger_id,
                authority_id,
                version,
                now.isoformat(),
                cooldown_until.isoformat(),
            ),
        )
        con.commit()
        con.close()
```

**Step 4: Run test to verify it passes**

```bash
./.venv/bin/python -m pytest tests/signals/test_suppression.py -v
```

**Step 5: Commit**

```bash
git add schema.sql src/signals/suppression.py tests/signals/test_suppression.py
git commit -m "feat(signals): add suppression manager with cooldown and version awareness"
```

---

## Phase 4: Adapters

### Task 4.1: Hearings Adapter

**Files:**
- Create: `src/signals/adapters/__init__.py`
- Create: `src/signals/adapters/hearings.py`
- Create: `tests/signals/test_adapters/__init__.py`
- Create: `tests/signals/test_adapters/test_hearings.py`

**Step 1: Write the failing test**

```python
# tests/signals/test_adapters/test_hearings.py
"""Tests for hearings adapter."""

import pytest
from src.signals.adapters.hearings import HearingsAdapter
from src.signals.envelope import Envelope


def test_adapt_hearing_to_envelope():
    adapter = HearingsAdapter()
    hearing = {
        "event_id": "HVAC-2026-01-15-001",
        "congress": 119,
        "chamber": "House",
        "committee_code": "HSVA",
        "committee_name": "House Veterans' Affairs",
        "hearing_date": "2026-01-20",
        "hearing_time": "10:00",
        "title": "Oversight of VA Disability Claims",
        "meeting_type": "hearing",
        "status": "scheduled",
        "location": "Room 334",
        "url": "https://veterans.house.gov/events/...",
        "first_seen_at": "2026-01-15T12:00:00Z",
        "updated_at": "2026-01-15T12:00:00Z",
    }

    envelope = adapter.adapt(hearing)

    assert isinstance(envelope, Envelope)
    assert envelope.event_id == "hearing-HVAC-2026-01-15-001"
    assert envelope.authority_id == "HVAC-2026-01-15-001"
    assert envelope.authority_source == "house_veterans"
    assert envelope.authority_type == "hearing_notice"
    assert envelope.committee == "HVAC"
    assert envelope.metadata["status"] == "scheduled"


def test_adapt_hearing_maps_committee():
    adapter = HearingsAdapter()

    # House VA committee
    hearing = _make_hearing(committee_code="HSVA")
    env = adapter.adapt(hearing)
    assert env.committee == "HVAC"

    # Senate VA committee
    hearing = _make_hearing(committee_code="SSVA")
    env = adapter.adapt(hearing)
    assert env.committee == "SVAC"


def test_adapt_hearing_computes_version():
    adapter = HearingsAdapter()
    hearing = _make_hearing()

    # First version
    env1 = adapter.adapt(hearing, version=1)
    assert env1.version == 1

    # Updated version
    env2 = adapter.adapt(hearing, version=2)
    assert env2.version == 2


def _make_hearing(**overrides):
    base = {
        "event_id": "TEST-001",
        "congress": 119,
        "chamber": "House",
        "committee_code": "HSVA",
        "committee_name": "House Veterans' Affairs",
        "hearing_date": "2026-01-20",
        "title": "Test Hearing",
        "status": "scheduled",
        "first_seen_at": "2026-01-15T12:00:00Z",
        "updated_at": "2026-01-15T12:00:00Z",
    }
    base.update(overrides)
    return base
```

**Step 2: Run test to verify it fails**

**Step 3: Write minimal implementation**

```python
# src/signals/adapters/hearings.py
"""Hearings adapter - transforms hearing records to normalized envelopes."""

from typing import Optional

from src.signals.envelope import Envelope


# Committee code to standard committee mapping
COMMITTEE_MAP = {
    "HSVA": "HVAC",
    "SSVA": "SVAC",
}

# Committee code to authority source mapping
AUTHORITY_SOURCE_MAP = {
    "HSVA": "house_veterans",
    "SSVA": "senate_veterans",
}


class HearingsAdapter:
    """Adapts hearing records to normalized envelopes."""

    def adapt(self, hearing: dict, version: int = 1) -> Envelope:
        """Transform a hearing record to a normalized envelope."""
        event_id = hearing.get("event_id", "")
        committee_code = hearing.get("committee_code", "")

        # Map committee
        committee = COMMITTEE_MAP.get(committee_code)
        authority_source = AUTHORITY_SOURCE_MAP.get(committee_code, "congress_gov")

        # Build body text from available fields
        body_parts = []
        if hearing.get("title"):
            body_parts.append(hearing["title"])
        if hearing.get("committee_name"):
            body_parts.append(f"Committee: {hearing['committee_name']}")
        if hearing.get("location"):
            body_parts.append(f"Location: {hearing['location']}")
        body_text = "\n".join(body_parts)

        # Determine topics based on title keywords
        topics = self._extract_topics(hearing.get("title", ""))

        return Envelope(
            event_id=f"hearing-{event_id}",
            authority_id=event_id,
            authority_source=authority_source,
            authority_type="hearing_notice",
            title=hearing.get("title", ""),
            body_text=body_text,
            committee=committee,
            topics=topics,
            version=version,
            published_at=hearing.get("first_seen_at"),
            published_at_source="derived",
            event_start_at=self._build_event_time(hearing),
            source_url=hearing.get("url"),
            fetched_at=hearing.get("updated_at"),
            metadata={
                "status": hearing.get("status"),
                "meeting_type": hearing.get("meeting_type"),
                "chamber": hearing.get("chamber"),
                "congress": hearing.get("congress"),
            },
        )

    def _extract_topics(self, title: str) -> list[str]:
        """Extract topics from title keywords."""
        title_lower = title.lower()
        topics = []

        topic_keywords = {
            "disability_benefits": ["disability", "benefits", "claims"],
            "rating": ["rating", "vasrd", "schedule"],
            "exam_quality": ["exam", "c&p", "medical examination"],
            "claims_backlog": ["backlog", "processing", "wait time"],
            "appeals": ["appeal", "bva", "board"],
        }

        for topic, keywords in topic_keywords.items():
            if any(kw in title_lower for kw in keywords):
                topics.append(topic)

        return topics

    def _build_event_time(self, hearing: dict) -> Optional[str]:
        """Build ISO timestamp from hearing date/time."""
        date = hearing.get("hearing_date")
        time = hearing.get("hearing_time", "00:00")
        if date:
            return f"{date}T{time}:00Z"
        return None
```

```python
# src/signals/adapters/__init__.py
"""Event adapters for signals routing."""

from .hearings import HearingsAdapter

__all__ = ["HearingsAdapter"]
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add src/signals/adapters/ tests/signals/test_adapters/
git commit -m "feat(signals): add hearings adapter"
```

---

### Task 4.2: Bills Adapter

**Files:**
- Create: `src/signals/adapters/bills.py`
- Create: `tests/signals/test_adapters/test_bills.py`

(Similar pattern - adapt bill records to Envelope with authority_type="bill_text")

---

### Task 4.3: OM Events Adapter

**Files:**
- Create: `src/signals/adapters/om_events.py`
- Create: `tests/signals/test_adapters/test_om_events.py`

(Similar pattern - adapt om_events records to Envelope)

---

## Phase 5: Output Channels

### Task 5.1: Audit Log Writer

**Files:**
- Modify: `schema.sql` (add signal_audit_log table)
- Create: `src/signals/output/__init__.py`
- Create: `src/signals/output/audit_log.py`
- Create: `tests/signals/test_output/__init__.py`
- Create: `tests/signals/test_output/test_audit_log.py`

**Step 1: Add schema**

```sql
-- Signal audit log
CREATE TABLE IF NOT EXISTS signal_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    authority_id TEXT NOT NULL,
    indicator_id TEXT NOT NULL,
    trigger_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    fired_at TEXT NOT NULL,
    suppressed INTEGER NOT NULL DEFAULT 0,
    suppression_reason TEXT,
    explanation_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_signal_audit_trigger ON signal_audit_log(trigger_id, fired_at);
CREATE INDEX IF NOT EXISTS idx_signal_audit_event ON signal_audit_log(event_id);
```

**Step 2: Write test and implementation**

```python
# src/signals/output/audit_log.py
"""Audit log writer for signal triggers."""

import json
from datetime import datetime, timezone

from src.db import connect
from src.signals.engine.evaluator import EvaluationResult


def write_audit_log(
    event_id: str,
    authority_id: str,
    indicator_id: str,
    trigger_id: str,
    severity: str,
    result: EvaluationResult,
    suppressed: bool = False,
    suppression_reason: str = None,
) -> int:
    """Write a trigger fire to the audit log. Returns row ID."""
    explanation = {
        "matched_terms": result.matched_terms,
        "matched_discriminators": result.matched_discriminators,
        "passed_evaluators": result.passed_evaluators,
        "failed_evaluators": result.failed_evaluators,
        "evidence_map": result.evidence_map,
    }

    con = connect()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO signal_audit_log
        (event_id, authority_id, indicator_id, trigger_id, severity, fired_at, suppressed, suppression_reason, explanation_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            authority_id,
            indicator_id,
            trigger_id,
            severity,
            datetime.now(timezone.utc).isoformat(),
            1 if suppressed else 0,
            suppression_reason,
            json.dumps(explanation),
        ),
    )
    row_id = cur.lastrowid
    con.commit()
    con.close()
    return row_id
```

---

### Task 5.2: Slack Alert Formatter

**Files:**
- Create: `src/signals/output/slack.py`
- Create: `tests/signals/test_output/test_slack.py`

(Format explanation payload into Slack blocks, use existing notify_slack.py infrastructure)

---

## Phase 6: Router Integration

### Task 6.1: Router Core

**Files:**
- Create: `src/signals/router.py`
- Create: `tests/signals/test_router.py`

**Step 1: Write the failing test**

```python
# tests/signals/test_router.py
"""Tests for signals router."""

import pytest
from src.signals.router import SignalsRouter, RouteResult
from src.signals.envelope import Envelope


@pytest.fixture
def router():
    return SignalsRouter(categories=["oversight_accountability"])


@pytest.fixture
def gao_envelope():
    return Envelope(
        event_id="test-1",
        authority_id="AUTH-1",
        authority_source="congress_gov",
        authority_type="hearing_notice",
        title="Hearing on GAO Report",
        body_text="The GAO found issues with VA disability claims. This is an investigation.",
        committee="HVAC",
        topics=["disability_benefits"],
        version=1,
    )


def test_router_matches_trigger(router, gao_envelope):
    results = router.route(gao_envelope)
    assert len(results) > 0
    assert any(r.trigger_id == "formal_audit_signal" for r in results)


def test_router_returns_route_result(router, gao_envelope):
    results = router.route(gao_envelope)
    result = results[0]
    assert isinstance(result, RouteResult)
    assert result.indicator_id is not None
    assert result.trigger_id is not None
    assert result.severity in ["low", "medium", "high", "critical"]


def test_router_respects_indicator_condition(router):
    # Envelope from non-matching authority source
    env = Envelope(
        event_id="test-2",
        authority_id="AUTH-2",
        authority_source="govinfo",  # Not congress_gov
        authority_type="rule",
        title="Test Rule",
        body_text="GAO found issues",
        version=1,
    )
    results = router.route(env)
    # Should not match gao_oig_reference indicator (requires congress_gov source)
    assert not any(r.indicator_id == "gao_oig_reference" for r in results)
```

**Step 2: Write minimal implementation**

```python
# src/signals/router.py
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
```

---

### Task 6.2: CLI Runner

**Files:**
- Create: `src/run_signals.py`
- Create: `tests/test_run_signals.py`

(CLI entry point with subcommands: route, status, test-envelope)

---

## Verification Checklist

After completing all tasks, verify:

- [ ] `make test` passes (all new tests)
- [ ] Engine rejects evaluators not in whitelist
- [ ] Engine rejects field access outside policy
- [ ] All triggers produce complete explanation payloads
- [ ] Suppression prevents duplicate alerts within cooldown
- [ ] Version-aware suppression re-alerts on content changes
- [ ] Labeled discriminator nodes populate matched_discriminators correctly
- [ ] Audit log captures all fired triggers (including suppressed)
- [ ] `python -m src.run_signals route --test-envelope` works end-to-end

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | 1.1-1.6 | Envelope, 7 evaluators, registry |
| 2 | 2.1-2.2 | Expression parser, evaluator engine |
| 3 | 3.1-3.2 | YAML schema loader, suppression manager |
| 4 | 4.1-4.3 | Adapters (hearings, bills, om_events) |
| 5 | 5.1-5.2 | Output channels (audit log, Slack) |
| 6 | 6.1-6.2 | Router core, CLI runner |

Total: ~18 tasks, each 2-5 minutes with TDD approach.
