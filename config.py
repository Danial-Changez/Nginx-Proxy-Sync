"""Config loaded from environment variables."""

import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

NPM_URL = os.environ["NPM_URL"]
NPM_EMAIL = os.environ["NPM_EMAIL"]
NPM_PASSWORD = os.environ["NPM_PASSWORD"]

NPM_DOMAIN = os.environ.get("NPM_DOMAIN", "")
DEFAULT_SCHEME = os.environ.get("NPM_DEFAULT_SCHEME", "http")
DEFAULT_CERT_NAME = os.environ.get("NPM_DEFAULT_CERT_NAME", "")

REMOTE_CONFIG = os.environ.get("NPM_REMOTE_CONFIG", "/config/remote-hosts.json")
DELETE_ORPHANS = os.environ.get("NPM_DELETE_ORPHANS", "false").lower() == "true"

TRUENAS_URL = os.environ.get("TRUENAS_URL", "")
TRUENAS_API_KEY = os.environ.get("TRUENAS_API_KEY", "")
TRUENAS_SKIP_APPS = set(
    filter(None, os.environ.get("TRUENAS_SKIP_APPS", "glances").split(","))
)

PIHOLE_URL = os.environ.get("PIHOLE_URL", "")
PIHOLE_PASSWORD = os.environ.get("PIHOLE_PASSWORD", "")
NPM_IP = os.environ.get("NPM_IP", "")

SYNC_INTERVAL = int(os.environ.get("NPM_SYNC_INTERVAL", "60"))

MANAGED_MARKER = "# managed-by:nginx-proxy-sync"
