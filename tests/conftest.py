"""Test setup: required configuration and a guard against real HTTP calls."""

import os

import pytest
import requests

# nginx_proxy_sync.config reads these at import time, so they must be set
# before any test module imports the package.
os.environ.update(
    NPM_URL="http://npm.invalid",
    NPM_EMAIL="admin@example.test",
    NPM_PASSWORD="unused",
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail loudly if a test reaches the real HTTP layer instead of a fake."""

    def refuse(self, method, url, **kwargs):
        raise AssertionError(f"unexpected HTTP request: {method} {url}")

    monkeypatch.setattr(requests.Session, "request", refuse)
