"""Docker label resolution and event handling against a faked Docker client."""

from types import SimpleNamespace

import pytest

from nginx_proxy_sync.discovery import DockerDiscovery
from nginx_proxy_sync.discovery import docker as docker_discovery
from nginx_proxy_sync.models import ProxyTarget

ENABLED = {"npm.enable": "true"}
BRIDGE = {"bridge": {"IPAddress": "172.17.0.2"}}


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    monkeypatch.setattr(docker_discovery, "NPM_DOMAIN", "example.test")
    monkeypatch.setattr(docker_discovery, "NPM_NETWORK", "")
    monkeypatch.setattr(docker_discovery, "DEFAULT_SCHEME", "http")
    # watch_events waits for a started container to get its network settings.
    monkeypatch.setattr(docker_discovery.time, "sleep", lambda seconds: None)


def container(name, labels=ENABLED, ports=("80/tcp",), networks=BRIDGE):
    return SimpleNamespace(
        name=name,
        labels=labels,
        attrs={
            "Config": {"ExposedPorts": {port: {} for port in ports}},
            "NetworkSettings": {"Networks": networks},
        },
    )


def event(status, name, labels=ENABLED):
    return {
        "status": status,
        "id": f"{name}-id".ljust(64, "0"),
        "Actor": {"Attributes": {"name": name, **labels}},
    }


def discovery(containers=(), events=()):
    """DockerDiscovery over a fake client with fixed containers and events."""
    by_id = {event("", c.name)["id"][:12]: c for c in containers}
    client = SimpleNamespace(
        containers=SimpleNamespace(
            list=lambda: list(containers), get=by_id.__getitem__
        ),
        events=lambda decode: iter(events),
    )
    return DockerDiscovery(client)


def watch(disc):
    """Run watch_events to the end of the fake stream; return the callbacks' calls."""
    started, stopped = [], []
    disc.watch_events(on_start=started.append, on_stop=stopped.append)
    return started, stopped


def test_discover_returns_only_enabled_containers_with_defaults():
    disc = discovery([container("whoami"), container("db", labels={})])

    assert disc.discover() == [
        ProxyTarget(
            host="whoami.example.test",
            port="80",
            forward_host="172.17.0.2",
            scheme="http",
        )
    ]


def test_labels_override_defaults():
    labels = {
        **ENABLED,
        "npm.host": "custom.example.org",
        "npm.port": "9000",
        "npm.scheme": "https",
        "npm.forward_host": "10.0.0.5",
    }

    assert discovery([container("whoami", labels)]).discover() == [
        ProxyTarget(
            host="custom.example.org",
            port="9000",
            forward_host="10.0.0.5",
            scheme="https",
        )
    ]


def test_forwards_by_container_name_on_the_shared_network(monkeypatch):
    monkeypatch.setattr(docker_discovery, "NPM_NETWORK", "proxy-net")
    networks = {"proxy-net": {"IPAddress": "172.18.0.3"}}

    [target] = discovery([container("whoami", networks=networks)]).discover()

    assert target.forward_host == "whoami"


@pytest.mark.parametrize(
    ("ports", "expected"),
    [
        (("443/tcp",), "443"),
        (("22/tcp", "443/tcp", "9000/tcp", "8080/tcp"), "8080"),
        (("22/tcp", "443/tcp"), "22"),
    ],
)
def test_port_is_detected_from_exposed_ports(ports, expected):
    [target] = discovery([container("whoami", ports=ports)]).discover()

    assert target.port == expected


def test_container_without_a_port_is_skipped():
    assert discovery([container("whoami", ports=())]).discover() == []


def test_start_event_reports_the_resolved_container():
    disc = discovery([container("whoami")], [event("start", "whoami")])

    started, stopped = watch(disc)

    assert [target.host for target in started] == ["whoami.example.test"]
    assert stopped == []


def test_stop_and_die_events_report_the_domain():
    custom = {**ENABLED, "npm.host": "custom.example.org"}
    disc = discovery(events=[event("stop", "whoami"), event("die", "api", custom)])

    started, stopped = watch(disc)

    assert started == []
    assert stopped == ["whoami.example.test", "custom.example.org"]


def test_unrelated_events_and_unlabelled_containers_are_ignored():
    disc = discovery(
        [container("db", labels={})],
        [
            event("create", "whoami"),
            event("destroy", "whoami"),
            event("start", "db", labels={}),
            event("die", "db", labels={}),
        ],
    )

    assert watch(disc) == ([], [])


def test_failing_callback_does_not_end_the_watch():
    disc = discovery(events=[event("die", "broken"), event("die", "whoami")])
    stopped = []

    def on_stop(domain):
        if domain.startswith("broken"):
            raise RuntimeError("NPM unavailable")
        stopped.append(domain)

    disc.watch_events(on_start=None, on_stop=on_stop)

    assert stopped == ["whoami.example.test"]
