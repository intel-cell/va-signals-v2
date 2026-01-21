"""Base class for state intelligence sources."""

from abc import ABC, abstractmethod

from src.state.common import RawSignal


class StateSource(ABC):
    """
    Abstract base class for state sources.

    Subclasses must implement:
        - source_id property: Unique identifier for this source
        - state property: State code (TX, CA, FL)
        - fetch() method: Returns list of RawSignal from the source
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique identifier for this source."""
        pass

    @property
    @abstractmethod
    def state(self) -> str:
        """State code (TX, CA, FL)."""
        pass

    @abstractmethod
    def fetch(self) -> list[RawSignal]:
        """Fetch signals from this source."""
        pass
