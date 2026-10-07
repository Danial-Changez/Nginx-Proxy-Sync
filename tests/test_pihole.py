"""Pi-hole DNS reconciliation with the HTTP layer faked."""

from types import SimpleNamespace
from urllib.parse import unquote

from nginx_proxy_sync.clients import PiholeClient
from nginx_proxy_sync.clients import pihole as pihole_client


def client_with_records(monkeypatch, records):
    """A PiholeClient whose requests are recorded and answered from `records`."""
    monkeypatch.setattr(pihole_client, "PIHOLE_URL", "http://pihole.invalid")
    monkeypatch.setattr(pihole_client, "PIHOLE_PASSWORD", "unused")
    monkeypatch.setattr(pihole_client, "NPM_IP", "10.0.0.2")
    client = PiholeClient()
    writes = []

    def fake_request(method, path):
        if method != "GET":
            writes.append((method, unquote(path.removeprefix("/config/dns/hosts/"))))
        return SimpleNamespace(json=lambda: {"config": {"dns": {"hosts": records}}})

    monkeypatch.setattr(client, "_request", fake_request)
    return client, writes


def test_sync_domains_adds_repoints_and_removes_stale(monkeypatch):
    client, writes = client_with_records(
        monkeypatch,
        [
            "10.0.0.2 kept.example.test",
            "10.0.0.9 moved.example.test",
            "10.0.0.2 stale.example.test",
        ],
    )

    client.sync_domains({"kept.example.test", "moved.example.test", "new.example.test"})

    assert sorted(writes) == [
        ("DELETE", "10.0.0.2 stale.example.test"),
        ("DELETE", "10.0.0.9 moved.example.test"),
        ("PUT", "10.0.0.2 moved.example.test"),
        ("PUT", "10.0.0.2 new.example.test"),
    ]
