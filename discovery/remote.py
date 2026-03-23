"""Discover proxy targets from a static JSON config file."""

import json
import os
import logging

from config import REMOTE_CONFIG, DEFAULT_SCHEME
from models import ProxyTarget
from discovery.base import DiscoverySource

log = logging.getLogger("nginx-proxy-sync")


class RemoteDiscovery(DiscoverySource):
    def discover(self) -> list[ProxyTarget]:
        """Load remote host definitions from JSON config file."""
        if not os.path.exists(REMOTE_CONFIG):
            log.info("No remote config at %s, skipping", REMOTE_CONFIG)
            return []

        with open(REMOTE_CONFIG) as f:
            entries = json.load(f)

        results = []
        for entry in entries:
            results.append(ProxyTarget(
                host=entry["host"],
                port=str(entry["forward_port"]),
                forward_host=entry["forward_host"],
                scheme=entry.get("forward_scheme", DEFAULT_SCHEME),
            ))

        log.info("Loaded %d remote host(s) from %s", len(results), REMOTE_CONFIG)
        return results
