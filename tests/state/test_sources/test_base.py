"""Tests for base source class."""

import pytest
from abc import ABC

from src.state.sources.base import StateSource
from src.state.common import RawSignal


def test_state_source_is_abstract():
    """StateSource should be abstract and not instantiable."""
    with pytest.raises(TypeError):
        StateSource()


def test_state_source_subclass():
    """Subclass must implement fetch method."""

    class TestSource(StateSource):
        source_id = "test_source"
        state = "TX"

        def fetch(self):
            return [
                RawSignal(
                    url="https://example.com/1",
                    title="Test Signal",
                    source_id=self.source_id,
                    state=self.state,
                )
            ]

    source = TestSource()
    signals = source.fetch()

    assert len(signals) == 1
    assert signals[0].state == "TX"
