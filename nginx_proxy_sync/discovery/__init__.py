"""Discovery sources for proxy host targets."""

from nginx_proxy_sync.discovery.base import DiscoverySource
from nginx_proxy_sync.discovery.docker import DockerDiscovery
from nginx_proxy_sync.discovery.remote import RemoteDiscovery
from nginx_proxy_sync.discovery.truenas import TrueNASDiscovery

__all__ = ["DiscoverySource", "DockerDiscovery", "RemoteDiscovery", "TrueNASDiscovery"]
