"""Pi-hole v6 API client - manages local DNS records."""

import logging
import requests
from urllib.parse import quote
from config import PIHOLE_URL, PIHOLE_PASSWORD, NPM_IP

log = logging.getLogger("nginx-proxy-sync")

class PiholeClient:
    def __init__(self):
        self._sid = None

    @property
    def enabled(self):
        return bool(PIHOLE_URL and PIHOLE_PASSWORD)

    def _authenticate(self):
        resp = requests.post(
            f"{PIHOLE_URL}/api/auth",
            json={"password": PIHOLE_PASSWORD},
            timeout=10,
        )
        resp.raise_for_status()
        self._sid = resp.json()["session"]["sid"]

    def _headers(self):
        if not self._sid:
            self._authenticate()
        return {"sid": self._sid}

    def _request(self, method, path, retry=True):
        """Make an authenticated request, re-auth on 401."""
        url = f"{PIHOLE_URL}/api{path}"
        resp = requests.request(method, url, headers=self._headers(), timeout=10)
        if resp.status_code == 401 and retry:
            self._authenticate()
            resp = requests.request(method, url, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp

    def list_hosts(self):
        """Return set of domains that have local DNS entries."""
        resp = self._request("GET", "/config/dns/hosts")
        entries = resp.json().get("config", {}).get("dns", {}).get("hosts", [])
        domains = set()
        for entry in entries:
            parts = entry.split(None, 1)
            if len(parts) == 2:
                domains.add(parts[1])
        return domains

    def add_host(self, domain):
        """Add a local DNS entry pointing domain to NPM_IP."""
        entry = quote(f"{NPM_IP} {domain}")
        self._request("PUT", f"/config/dns/hosts/{entry}")
        log.info("Pi-hole DNS added: %s -> %s", domain, NPM_IP)

    def remove_host(self, domain, ip=None):
        """Remove a local DNS entry for domain."""
        target_ip = ip or NPM_IP
        entry = quote(f"{target_ip} {domain}")
        try:
            self._request("DELETE", f"/config/dns/hosts/{entry}")
            log.info("Pi-hole DNS removed: %s", domain)
        except requests.HTTPError:
            log.debug("Pi-hole DNS entry not found for removal: %s", domain)

    def sync_domains(self, desired_domains):
        """Ensure all desired domains have local DNS entries.
        Add missing ones, remove stale ones that match NPM_IP."""
        if not self.enabled:
            return

        try:
            existing = self._list_entries_with_ip()
        except Exception as e:
            log.error("Failed to fetch Pi-hole DNS entries: %s", e)
            return

        for domain in desired_domains:
            if domain not in existing:
                try:
                    self.add_host(domain)
                except Exception as e:
                    log.error("Failed to add Pi-hole DNS for %s: %s", domain, e)
            elif existing[domain] != NPM_IP:
                try:
                    self.remove_host(domain, existing[domain])
                    self.add_host(domain)
                except Exception as e:
                    log.error("Failed to fix Pi-hole DNS for %s: %s", domain, e)

        for domain, ip in existing.items():
            if domain not in desired_domains:
                try:
                    self.remove_host(domain, ip)
                except Exception as e:
                    log.error("Failed to remove Pi-hole DNS for %s: %s", domain, e)

    def _list_entries_with_ip(self):
        """Return dict of domain -> ip for all local DNS entries."""
        resp = self._request("GET", "/config/dns/hosts")
        entries = resp.json().get("config", {}).get("dns", {}).get("hosts", [])
        result = {}
        for entry in entries:
            parts = entry.split(None, 1)
            if len(parts) == 2:
                result[parts[1]] = parts[0]
        return result
