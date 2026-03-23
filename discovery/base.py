"""Abstract base class for discovery sources."""

from abc import ABC, abstractmethod

from models import ProxyTarget


class DiscoverySource(ABC):
    """Base class for all service discovery backends."""

    @abstractmethod
    def discover(self) -> list[ProxyTarget]:
        """Return a list of discovered proxy targets."""
