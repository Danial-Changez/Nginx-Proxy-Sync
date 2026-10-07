"""API clients for external services."""

from nginx_proxy_sync.clients.npm import NPMClient
from nginx_proxy_sync.clients.pihole import PiholeClient

__all__ = ["NPMClient", "PiholeClient"]
