"""Discover proxy targets from local Docker containers via labels."""

import time
import logging

from config import NPM_DOMAIN, DEFAULT_SCHEME
from models import ProxyTarget
from discovery.base import DiscoverySource

log = logging.getLogger("nginx-proxy-sync")


class DockerDiscovery(DiscoverySource):
    def __init__(self, client):
        self.client = client

    def discover(self) -> list[ProxyTarget]:
        """Return list of proxy targets from labeled containers."""
        results = []
        for container in self.client.containers.list():
            target = self._resolve(container)
            if target:
                results.append(target)
        return results

    def watch_events(self, on_start, on_stop):
        """Block and watch Docker events, calling callbacks on npm-enabled container lifecycle."""
        log.info("Watching Docker events...")
        for event in self.client.events(decode=True):
            status = event.get("status")
            if status not in ("start", "stop", "die"):
                continue

            actor = event.get("Actor", {}).get("Attributes", {})
            if actor.get("npm.enable", "").lower() != "true":
                continue

            container_id = event.get("id", "")[:12]
            name = actor.get("name", container_id)
            log.info("Event: %s %s", status, name)

            if status == "start":
                time.sleep(2)
                try:
                    container = self.client.containers.get(container_id)
                    target = self._resolve(container)
                    if target:
                        on_start(target)
                except Exception as e:
                    log.error("Error handling start for %s: %s", name, e)

            elif status in ("stop", "die"):
                domain = actor.get("npm.host") or f"{name}.{NPM_DOMAIN}"
                try:
                    on_stop(domain)
                except Exception as e:
                    log.error("Error handling stop for %s: %s", name, e)

    def _resolve(self, container) -> ProxyTarget | None:
        """Build proxy target from container labels + defaults."""
        labels = container.labels or {}
        if labels.get("npm.enable", "").lower() != "true":
            return None

        host = labels.get("npm.host") or f"{container.name}.{NPM_DOMAIN}"
        port = labels.get("npm.port") or self._detect_port(container)
        if not port:
            log.warning("Container %s: npm.enable=true but no port detectable, skipping", container.name)
            return None

        forward_host = labels.get("npm.forward_host") or self._get_ip(container)
        scheme = labels.get("npm.scheme", DEFAULT_SCHEME)

        return ProxyTarget(
            host=host,
            port=port,
            forward_host=forward_host,
            scheme=scheme,
        )

    @staticmethod
    def _detect_port(container):
        """Auto-detect the exposed port from container config."""
        exposed = container.attrs.get("Config", {}).get("ExposedPorts") or {}
        ports = []
        for spec in exposed:
            try:
                ports.append(int(spec.split("/")[0]))
            except (ValueError, IndexError):
                continue
        if not ports:
            return None
        if len(ports) == 1:
            return str(ports[0])
        skip = {22, 443}
        filtered = [p for p in ports if p not in skip]
        return str(min(filtered or ports))

    @staticmethod
    def _get_ip(container):
        """Get the container's IP on the first available network."""
        networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
        for info in networks.values():
            ip = info.get("IPAddress")
            if ip:
                return ip
        return container.name
