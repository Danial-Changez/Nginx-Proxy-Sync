"""Reconcile decisions of SyncEngine against a faked NPM client."""

from dataclasses import replace

import pytest
import requests

from nginx_proxy_sync import sync
from nginx_proxy_sync.clients import NPMClient
from nginx_proxy_sync.config import MANAGED_MARKER
from nginx_proxy_sync.discovery import DiscoverySource
from nginx_proxy_sync.models import ProxyTarget
from nginx_proxy_sync.sync import SyncEngine

APP = ProxyTarget(host="app.example.test", port="8080", forward_host="10.0.0.5")
OTHER = ProxyTarget(host="other.example.test", port="3000", forward_host="10.0.0.6")


class FakeNPM(NPMClient):
    """NPMClient with its HTTP calls replaced by an in-memory host list.

    Hosts are stored exactly as the real client would send them, so the
    managed marker is exercised end to end.
    """

    def __init__(self, hosts=()):
        super().__init__()
        self.hosts = list(hosts)
        self.writes = []

    def list_hosts(self):
        return list(self.hosts)

    def create_host(self, domain, forward_host, forward_port, scheme="http"):
        payload = self._base_payload(domain, forward_host, forward_port, scheme)
        self.hosts.append({"id": 100 + len(self.hosts), **payload})
        self.writes.append(("create", domain, forward_host, forward_port, scheme))

    def update_host(self, host_id, domain, forward_host, forward_port, scheme="http"):
        payload = self._base_payload(domain, forward_host, forward_port, scheme)
        self.hosts = [
            {"id": host_id, **payload} if host["id"] == host_id else host
            for host in self.hosts
        ]
        self.writes.append(
            ("update", host_id, domain, forward_host, forward_port, scheme)
        )

    def delete_host(self, host_id, domain):
        self.hosts = [host for host in self.hosts if host["id"] != host_id]
        self.writes.append(("delete", host_id, domain))


class RecordingPihole:
    def __init__(self):
        self.synced = None
        self.added = []
        self.removed = []

    def sync_domains(self, domains):
        self.synced = set(domains)

    def add_host(self, domain):
        self.added.append(domain)

    def remove_host(self, domain):
        self.removed.append(domain)


class StaticSource(DiscoverySource):
    def __init__(self, *targets):
        self.targets = targets

    def discover(self):
        return list(self.targets)


def npm_host(host_id, domain, advanced_config=MANAGED_MARKER, **overrides):
    """A proxy host as the NPM API returns it (note the integer port)."""
    return {
        "id": host_id,
        "domain_names": [domain],
        "forward_host": "10.0.0.5",
        "forward_port": 8080,
        "forward_scheme": "http",
        "advanced_config": advanced_config,
        **overrides,
    }


def engine(npm, *targets, pihole=None):
    return SyncEngine(npm, [StaticSource(*targets)], pihole=pihole)


def test_desired_state_merges_sources_and_last_source_wins():
    moved = replace(APP, forward_host="10.0.0.9")
    sources = [StaticSource(APP, OTHER), StaticSource(moved)]

    desired = SyncEngine(FakeNPM(), sources).build_desired_state()

    assert desired == {APP.host: moved, OTHER.host: OTHER}


def test_created_host_is_managed_on_later_syncs():
    npm = FakeNPM()
    source = StaticSource(APP)
    eng = SyncEngine(npm, [source])

    eng.sync()
    eng.sync()
    source.targets = (replace(APP, forward_host="10.0.0.9"),)
    eng.sync()

    assert npm.writes == [
        ("create", "app.example.test", "10.0.0.5", "8080", "http"),
        ("update", 100, "app.example.test", "10.0.0.9", "8080", "http"),
    ]


@pytest.mark.parametrize(
    "drift",
    [{"forward_host": "10.0.0.9"}, {"forward_port": 9090}, {"forward_scheme": "https"}],
)
def test_sync_updates_managed_host_that_drifted(drift):
    npm = FakeNPM([npm_host(7, APP.host, **drift)])
    eng = engine(npm, APP)

    eng.sync()
    eng.sync()

    assert npm.writes == [("update", 7, "app.example.test", "10.0.0.5", "8080", "http")]


@pytest.mark.parametrize("advanced_config", [None, "", "client_max_body_size 1g;"])
def test_sync_never_updates_host_without_marker(advanced_config):
    npm = FakeNPM([npm_host(7, APP.host, advanced_config, forward_host="10.0.0.9")])

    engine(npm, APP).sync()

    assert npm.writes == []


def test_orphans_are_kept_unless_deletion_is_enabled(monkeypatch):
    monkeypatch.setattr(sync, "DELETE_ORPHANS", False)
    npm = FakeNPM([npm_host(1, "gone.example.test")])

    engine(npm).sync()

    assert npm.writes == []


def test_only_managed_orphans_are_deleted(monkeypatch):
    monkeypatch.setattr(sync, "DELETE_ORPHANS", True)
    npm = FakeNPM(
        [
            npm_host(1, "gone.example.test"),
            npm_host(2, "manual.example.test", advanced_config=""),
            npm_host(3, APP.host),
        ]
    )

    engine(npm, APP).sync()

    assert npm.writes == [("delete", 1, "gone.example.test")]


def test_sync_continues_after_a_failed_write(monkeypatch):
    npm = FakeNPM()
    create_host = npm.create_host

    def fail_for_app(domain, *args):
        if domain == APP.host:
            raise requests.HTTPError("500 Server Error")
        create_host(domain, *args)

    monkeypatch.setattr(npm, "create_host", fail_for_app)

    engine(npm, APP, OTHER).sync()

    assert npm.writes == [("create", "other.example.test", "10.0.0.6", "3000", "http")]


def test_sync_sends_managed_and_manual_domains_to_pihole():
    npm = FakeNPM([npm_host(2, "manual.example.test", advanced_config="")])
    pihole = RecordingPihole()

    engine(npm, APP, pihole=pihole).sync()

    assert pihole.synced == {"app.example.test", "manual.example.test"}


def test_start_event_creates_host_only_if_missing():
    npm = FakeNPM()
    pihole = RecordingPihole()
    eng = engine(npm, pihole=pihole)

    eng.handle_start(APP)
    eng.handle_start(APP)

    assert npm.writes == [("create", "app.example.test", "10.0.0.5", "8080", "http")]
    assert pihole.added == ["app.example.test"]


def test_start_event_leaves_unmanaged_host_alone():
    npm = FakeNPM([npm_host(2, APP.host, advanced_config="", forward_host="10.0.0.9")])

    engine(npm).handle_start(APP)

    assert npm.writes == []


def test_stop_event_deletes_managed_host():
    npm = FakeNPM([npm_host(1, APP.host), npm_host(2, OTHER.host)])
    pihole = RecordingPihole()

    engine(npm, pihole=pihole).handle_stop(APP.host)

    assert npm.writes == [("delete", 1, "app.example.test")]
    assert pihole.removed == ["app.example.test"]


def test_stop_event_never_deletes_unmanaged_host():
    npm = FakeNPM([npm_host(2, APP.host, advanced_config="")])
    pihole = RecordingPihole()

    engine(npm, pihole=pihole).handle_stop(APP.host)

    assert npm.writes == []
    assert pihole.removed == []
