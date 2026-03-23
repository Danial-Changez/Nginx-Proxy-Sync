"""Discover proxy targets from TrueNAS apps via API."""

import logging
from urllib.parse import urlparse

import requests

from config import TRUENAS_URL, TRUENAS_API_KEY, TRUENAS_SKIP_APPS, NPM_DOMAIN, DEFAULT_SCHEME
from models import ProxyTarget
from discovery.base import DiscoverySource

log = logging.getLogger("nginx-proxy-sync")


class TrueNASDiscovery(DiscoverySource):
    def discover(self) -> list[ProxyTarget]:
        """Query TrueNAS API and return proxy targets for running apps."""
        if not TRUENAS_URL or not TRUENAS_API_KEY:
            return []

        truenas_ip = urlparse(TRUENAS_URL).hostname

        try:
            resp = requests.get(
                f"{TRUENAS_URL}/api/v2.0/app",
                headers={"Authorization": f"Bearer {TRUENAS_API_KEY}"},
                verify=False,  # TrueNAS typically uses a self-signed cert
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            log.error("Failed to query TrueNAS API: %s", e)
            return []

        results = []
        for app in resp.json():
            name = app.get("name", "")
            if app.get("state") != "RUNNING" or name in TRUENAS_SKIP_APPS:
                continue

            port = self._find_web_port(app)
            if not port:
                continue

            results.append(ProxyTarget(
                host=f"{name}.{NPM_DOMAIN}",
                port=str(port),
                forward_host=truenas_ip,
                scheme=DEFAULT_SCHEME,
            ))

        log.info("Discovered %d TrueNAS app(s) from %s", len(results), TRUENAS_URL)
        return results

    @staticmethod
    def _find_web_port(app):
        """Find the first TCP host-mapped port for an app."""
        for port_info in app.get("active_workloads", {}).get("used_ports", []):
            if port_info.get("protocol") != "tcp":
                continue
            for hp in port_info.get("host_ports", []):
                if hp.get("host_ip") == "0.0.0.0":
                    return hp["host_port"]
        return None
