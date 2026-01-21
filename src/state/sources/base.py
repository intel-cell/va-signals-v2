"""Base class for state intelligence sources."""

from abc import ABC, abstractmethod

from src.state.common import RawSignal


class StateSource(ABC):
    """Abstract base class for state sources."""

    source_id: str
    state: str

    @abstractmethod
    def fetch(self) -> list[RawSignal]:
        """Fetch signals from this source."""
        pass
