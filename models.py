"""Shared data models for proxy target configuration."""

from dataclasses import dataclass


@dataclass
class ProxyTarget:
    """A discovered service that should be proxied."""

    host: str
    port: str
    forward_host: str
    scheme: str = "http"
