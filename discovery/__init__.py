"""Discovery sources for proxy host targets."""

from discovery.base import DiscoverySource
from discovery.docker import DockerDiscovery
from discovery.remote import RemoteDiscovery
from discovery.truenas import TrueNASDiscovery

__all__ = ["DiscoverySource", "DockerDiscovery", "RemoteDiscovery", "TrueNASDiscovery"]
