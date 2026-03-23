"""NPM API client - handles auth, CRUD for proxy hosts, and cert lookup."""

import time
import logging
import requests
from config import NPM_URL, NPM_EMAIL, NPM_PASSWORD, DEFAULT_CERT_NAME, MANAGED_MARKER

log = logging.getLogger("nginx-proxy-sync")

class NPMClient:
    def __init__(self):
        self._token = None
        self._token_expires = 0
        self.cert_id = 0

    def authenticate(self):
        resp = requests.post(
            f"{NPM_URL}/api/tokens",
            json={"identity": NPM_EMAIL, "secret": NPM_PASSWORD},
        )
        resp.raise_for_status()
        self._token = resp.json()["token"]
        self._token_expires = time.time() + 3500
        log.info("Authenticated with NPM")

    def _headers(self):
        if self._token is None or time.time() > self._token_expires:
            self.authenticate()
        return {"Authorization": f"Bearer {self._token}"}

    def lookup_cert(self):
        if not DEFAULT_CERT_NAME:
            log.info("No NPM_DEFAULT_CERT_NAME set, SSL certs will not be assigned")
            return

        resp = requests.get(f"{NPM_URL}/api/nginx/certificates", headers=self._headers())
        resp.raise_for_status()

        for cert in resp.json():
            if DEFAULT_CERT_NAME in cert.get("domain_names", []):
                self.cert_id = cert["id"]
                log.info("Found wildcard cert '%s' with id=%d", DEFAULT_CERT_NAME, self.cert_id)
                return
            if DEFAULT_CERT_NAME in cert.get("nice_name", ""):
                self.cert_id = cert["id"]
                log.info("Found cert '%s' (nice_name match) with id=%d", cert["nice_name"], self.cert_id)
                return

        log.warning("Certificate '%s' not found, hosts will be created without SSL cert", DEFAULT_CERT_NAME)

    def list_hosts(self):
        resp = requests.get(f"{NPM_URL}/api/nginx/proxy-hosts", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def _base_payload(self, domain, forward_host, forward_port, scheme):
        return {
            "domain_names": [domain],
            "forward_host": forward_host,
            "forward_port": int(forward_port),
            "forward_scheme": scheme,
            "access_list_id": 0,
            "certificate_id": self.cert_id,
            "ssl_forced": self.cert_id > 0,
            "http2_support": self.cert_id > 0,
            "block_exploits": True,
            "allow_websocket_upgrade": True,
            "meta": {"letsencrypt_agree": False, "dns_challenge": False},
            "advanced_config": MANAGED_MARKER,
            "locations": [],
            "caching_enabled": False,
            "hsts_enabled": False,
            "hsts_subdomains": False,
        }

    def create_host(self, domain, forward_host, forward_port, scheme="http"):
        payload = self._base_payload(domain, forward_host, forward_port, scheme)
        resp = requests.post(
            f"{NPM_URL}/api/nginx/proxy-hosts",
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        log.info("Created proxy host: %s -> %s:%s (%s)", domain, forward_host, forward_port, scheme)
        return resp.json()

    def update_host(self, host_id, domain, forward_host, forward_port, scheme="http"):
        payload = self._base_payload(domain, forward_host, forward_port, scheme)
        resp = requests.put(
            f"{NPM_URL}/api/nginx/proxy-hosts/{host_id}",
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        log.info("Updated proxy host: %s -> %s:%s (%s)", domain, forward_host, forward_port, scheme)
        return resp.json()

    def delete_host(self, host_id, domain):
        resp = requests.delete(
            f"{NPM_URL}/api/nginx/proxy-hosts/{host_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        log.info("Deleted proxy host: %s (id=%s)", domain, host_id)
