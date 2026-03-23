"""Discovery sources for proxy host targets."""

from discovery.base import DiscoverySource
from discovery.docker import DockerDiscovery
from discovery.truenas import TrueNASDiscovery
from discovery.remote import RemoteDiscovery

__all__ = ["DiscoverySource", "DockerDiscovery", "TrueNASDiscovery", "RemoteDiscovery"]
