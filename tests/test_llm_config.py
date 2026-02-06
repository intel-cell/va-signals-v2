"""Tests for central LLM model version configuration."""

import re

from src.llm_config import SONNET_MODEL, HAIKU_MODEL, HAIKU_LEGACY_MODEL

MODEL_PATTERN = re.compile(r"^claude-.+-.+$")


def test_constants_are_nonempty_strings():
    for name, val in [
        ("SONNET_MODEL", SONNET_MODEL),
        ("HAIKU_MODEL", HAIKU_MODEL),
        ("HAIKU_LEGACY_MODEL", HAIKU_LEGACY_MODEL),
    ]:
        assert isinstance(val, str) and len(val) > 0, f"{name} must be a non-empty string"


def test_model_string_format():
    for name, val in [
        ("SONNET_MODEL", SONNET_MODEL),
        ("HAIKU_MODEL", HAIKU_MODEL),
        ("HAIKU_LEGACY_MODEL", HAIKU_LEGACY_MODEL),
    ]:
        assert MODEL_PATTERN.match(val), f"{name} ({val}) must match claude-*-* format"


def test_summarize_uses_central_config():
    from src.summarize import CLAUDE_MODEL
    assert CLAUDE_MODEL == SONNET_MODEL


def test_agenda_drift_uses_central_config():
    from src.agenda_drift import CLAUDE_MODEL
    assert CLAUDE_MODEL == SONNET_MODEL


def test_deviation_uses_central_config():
    from src.oversight.pipeline.deviation import SONNET_MODEL as DEV_MODEL
    assert DEV_MODEL == SONNET_MODEL


def test_classifier_uses_central_config():
    from src.oversight.pipeline.classifier import HAIKU_MODEL as CLS_MODEL
    assert CLS_MODEL == HAIKU_MODEL


def test_state_classify_uses_central_config():
    from src.state.classify import HAIKU_MODEL as STATE_MODEL
    assert STATE_MODEL == HAIKU_LEGACY_MODEL
