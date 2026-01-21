"""Tests for base source class."""

import pytest

from src.state.sources.base import StateSource
from src.state.common import RawSignal


def test_state_source_is_abstract():
    """StateSource should be abstract and not instantiable."""
    with pytest.raises(TypeError):
        StateSource()


def test_state_source_subclass():
    """Subclass must implement properties and fetch method."""

    class TestSource(StateSource):
        @property
        def source_id(self) -> str:
            return "test_source"

        @property
        def state(self) -> str:
            return "TX"

        def fetch(self) -> list[RawSignal]:
            return [
                RawSignal(
                    url="https://example.com/1",
                    title="Test Signal",
                    source_id=self.source_id,
                    state=self.state,
                )
            ]

    source = TestSource()

    # Verify properties are accessible
    assert source.source_id == "test_source"
    assert source.state == "TX"

    # Verify fetch works
    signals = source.fetch()
    assert len(signals) == 1
    assert signals[0].state == "TX"
    assert signals[0].source_id == "test_source"


def test_state_source_missing_implementation():
    """Subclass missing required properties cannot be instantiated."""

    class IncompleteSource(StateSource):
        def fetch(self) -> list[RawSignal]:
            return []

        # Missing source_id and state properties

    with pytest.raises(TypeError):
        IncompleteSource()
