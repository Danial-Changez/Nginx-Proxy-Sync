"""Sync engine - reconciles desired proxy state with NPM."""

import logging
import requests
from config import MANAGED_MARKER, DELETE_ORPHANS
from clients.npm import NPMClient
from models import ProxyTarget
from discovery.base import DiscoverySource

log = logging.getLogger("nginx-proxy-sync")


class SyncEngine:
    def __init__(self, npm: NPMClient, sources: list[DiscoverySource], pihole=None):
        self.npm = npm
        self.sources = sources
        self.pihole = pihole

    def build_desired_state(self) -> dict[str, ProxyTarget]:
        """Merge all discovery sources into a single desired state dict."""
        desired = {}
        for source in self.sources:
            for target in source.discover():
                desired[target.host] = target
        return desired

    def sync(self):
        """Full reconciliation: create, update, delete."""
        existing = self.npm.list_hosts()
        existing_by_domain = {}
        for h in existing:
            for d in h.get("domain_names", []):
                existing_by_domain[d] = h

        desired = self.build_desired_state()
        created = updated = deleted = 0

        for domain, target in desired.items():
            if domain in existing_by_domain:
                ex = existing_by_domain[domain]
                if _is_managed(ex) and _needs_update(ex, target):
                    try:
                        self.npm.update_host(ex["id"], domain, target.forward_host, target.port, target.scheme)
                        updated += 1
                    except requests.HTTPError as e:
                        log.error("Failed to update %s: %s", domain, e)
            else:
                try:
                    self.npm.create_host(domain, target.forward_host, target.port, target.scheme)
                    created += 1
                except requests.HTTPError as e:
                    log.error("Failed to create %s: %s", domain, e)

        if DELETE_ORPHANS:
            for domain, ex in existing_by_domain.items():
                if domain not in desired and _is_managed(ex):
                    try:
                        self.npm.delete_host(ex["id"], domain)
                        deleted += 1
                    except requests.HTTPError as e:
                        log.error("Failed to delete orphan %s: %s", domain, e)

        log.info(
            "Sync complete: %d desired, %d existing, %d created, %d updated, %d deleted",
            len(desired), len(existing), created, updated, deleted,
        )

        # Sync Pi-hole DNS for ALL NPM proxy host domains (managed + manual)
        if self.pihole:
            all_domains = set(desired.keys())
            for h in self.npm.list_hosts():
                all_domains.update(h.get("domain_names", []))
            self.pihole.sync_domains(all_domains)

    def handle_start(self, target: ProxyTarget):
        """Handle a container start event - create host if missing."""
        existing = self.npm.list_hosts()
        if any(target.host in h.get("domain_names", []) for h in existing):
            return
        self.npm.create_host(target.host, target.forward_host, target.port, target.scheme)
        if self.pihole:
            try:
                self.pihole.add_host(target.host)
            except Exception as e:
                log.error("Failed to add Pi-hole DNS for %s: %s", target.host, e)

    def handle_stop(self, domain):
        """Handle a container stop event - delete managed host."""
        for h in self.npm.list_hosts():
            if domain in h.get("domain_names", []) and _is_managed(h):
                self.npm.delete_host(h["id"], domain)
                if self.pihole:
                    try:
                        self.pihole.remove_host(domain)
                    except Exception as e:
                        log.error("Failed to remove Pi-hole DNS for %s: %s", domain, e)
                break


def _is_managed(host):
    return MANAGED_MARKER in (host.get("advanced_config") or "")


def _needs_update(existing, target: ProxyTarget):
    return (
        existing.get("forward_host") != target.forward_host
        or str(existing.get("forward_port")) != str(target.port)
        or existing.get("forward_scheme") != target.scheme
    )
