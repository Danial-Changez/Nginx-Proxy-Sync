"""
NPM Assistant - auto-discovers services and manages Nginx Proxy Manager
proxy hosts from multiple sources:

  1. Docker containers with  npm.enable: "true"  label
  2. TrueNAS apps discovered via the TrueNAS API

Anything else (remote VMs, host-network services) should be added
manually via the NPM UI. The assistant won't touch unmanaged entries.

Per-service label overrides:
  npm.host         custom domain (overrides auto-derived name)
  npm.port         forward port  (overrides auto-detected port)
  npm.scheme       forward scheme (overrides NPM_DEFAULT_SCHEME)
  npm.forward_host forward IP    (overrides container IP detection)
"""

import argparse
import json
import os
import sys
import time
import logging
import threading

import urllib3
import docker

# Suppress warnings from TrueNAS self-signed cert requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import NPM_DOMAIN, SYNC_INTERVAL
from clients import NPMClient, PiholeClient
from sync import SyncEngine
from discovery import DockerDiscovery, TrueNASDiscovery

log = logging.getLogger("nginx-proxy-sync")


def backup_hosts(npm: NPMClient):
    """Save a snapshot of all proxy hosts to /data/npm-backup-latest.json."""
    hosts = npm.list_hosts()
    if not hosts:
        log.info("No proxy hosts to backup")
        return hosts

    os.makedirs("/data", exist_ok=True)
    # Timestamped copy + latest symlink-style overwrite
    ts_file = f"/data/npm-backup-{int(time.time())}.json"
    latest_file = "/data/npm-backup-latest.json"
    for path in (ts_file, latest_file):
        with open(path, "w") as f:
            json.dump(hosts, f, indent=2)
    log.info("Backed up %d hosts to %s", len(hosts), ts_file)
    return hosts


def backup_and_purge(npm: NPMClient):
    """Export all proxy hosts to JSON, then delete them all."""
    hosts = backup_hosts(npm)
    if not hosts:
        return

    for h in hosts:
        domains = ", ".join(h.get("domain_names", []))
        try:
            npm.delete_host(h["id"], domains)
        except Exception as e:
            log.error("Failed to delete %s: %s", domains, e)

    log.info("Purge complete")


def main():
    parser = argparse.ArgumentParser(description="Nginx Proxy Sync")
    parser.add_argument("--backup-and-purge", action="store_true",
                        help="Backup all proxy hosts to JSON and delete them, then exit")
    args = parser.parse_args()

    log.info("Nginx Proxy Sync starting")
    if NPM_DOMAIN:
        log.info("Domain: %s", NPM_DOMAIN)

    # Wait for NPM
    npm = NPMClient()
    for attempt in range(30):
        try:
            npm.authenticate()
            break
        except Exception:
            log.info("Waiting for NPM... (attempt %d/30)", attempt + 1)
            time.sleep(5)
    else:
        log.error("Could not connect to NPM after 30 attempts")
        sys.exit(1)

    if args.backup_and_purge:
        backup_and_purge(npm)
        return

    npm.lookup_cert()

    # Backup current state before any sync changes
    backup_hosts(npm)

    pihole = PiholeClient()
    if pihole.enabled:
        log.info("Pi-hole DNS sync enabled")

    client = docker.from_env()
    docker_disc = DockerDiscovery(client)
    sources = [docker_disc, TrueNASDiscovery()]
    engine = SyncEngine(npm, sources, pihole=pihole if pihole.enabled else None)

    engine.sync()

    def periodic_sync():
        while True:
            time.sleep(SYNC_INTERVAL)
            try:
                log.info("Running periodic sync")
                engine.sync()
            except Exception as e:
                log.error("Periodic sync error: %s", e)

    sync_thread = threading.Thread(target=periodic_sync, daemon=True)
    sync_thread.start()
    log.info("Periodic sync every %ds", SYNC_INTERVAL)

    while True:
        try:
            docker_disc.watch_events(
                on_start=engine.handle_start,
                on_stop=engine.handle_stop,
            )
        except Exception as e:
            log.error("Event watch error: %s, restarting in 10s...", e)
            time.sleep(10)


if __name__ == "__main__":
    main()
