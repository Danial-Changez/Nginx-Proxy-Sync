# Nginx Proxy Sync

Keeps [Nginx Proxy Manager](https://github.com/NginxProxyManager/nginx-proxy-manager) (NPM) proxy hosts, and optionally Pi-hole local DNS records, in step with the services that are actually running. It discovers Docker containers by label and TrueNAS apps through the TrueNAS API, then creates, updates and deletes proxy hosts through the NPM REST API.

## How it works

1. On start it logs in to NPM (up to 30 attempts, 5 seconds apart), looks up the certificate named by `NPM_DEFAULT_CERT_NAME`, and writes any existing proxy hosts to `/data/npm-backup-<timestamp>.json` and `/data/npm-backup-latest.json`.
2. It runs a full sync, then repeats it every `NPM_SYNC_INTERVAL` seconds:
   - a discovered service whose domain has no proxy host gets one;
   - a managed host whose forward host, port or scheme no longer matches its service is updated;
   - with `NPM_DELETE_ORPHANS=true`, a managed host whose service is gone is deleted.
3. Between syncs it follows Docker events. A labelled container that starts gets a proxy host if its domain has none. One that stops or dies has its managed host deleted, whatever `NPM_DELETE_ORPHANS` is set to.

Hosts created by this tool carry the marker `# managed-by:nginx-proxy-sync` in NPM's advanced-config field. Syncing and event handling only update or delete hosts that carry it, so a host you created by hand is left alone even if a discovered service uses the same domain.

The one exception is `python -m nginx_proxy_sync --backup-and-purge`, which backs up and then deletes **every** proxy host, managed or not, and exits.

### Pi-hole

When `PIHOLE_URL` and `PIHOLE_PASSWORD` are set, each sync also gives every discovered domain and every NPM proxy-host domain (managed or not) a Pi-hole v6 local DNS record pointing at `NPM_IP`, and removes records pointing at `NPM_IP` whose domain is no longer in that set. Records for other domains that point elsewhere are not touched.

## Docker labels

| Label | Default | Description |
|---|---|---|
| `npm.enable` | - | Must be `"true"` for the container to be discovered |
| `npm.host` | `<container name>.<NPM_DOMAIN>` | Domain of the proxy host |
| `npm.port` | detected | Forward port. Detected from the exposed ports: the only one, or else the lowest that is not 22 or 443. A container with no exposed port and no label is skipped. |
| `npm.scheme` | `NPM_DEFAULT_SCHEME` | Forward scheme |
| `npm.forward_host` | detected | Forward address. Detected as the container name if the container is on `NPM_NETWORK`, otherwise its IP address. |

TrueNAS apps need no labels: each app in state `RUNNING` is proxied as `<app name>.<NPM_DOMAIN>`, forwarding to the host of `TRUENAS_URL` on the app's first TCP port published on `0.0.0.0`.

## Configuration

All configuration is read from environment variables at start-up.

| Variable | Default | Description |
|---|---|---|
| `NPM_URL` | required | Base URL of the NPM admin API, e.g. `http://npm:81` |
| `NPM_EMAIL` | required | NPM account email |
| `NPM_PASSWORD` | required | NPM account password |
| `NPM_DOMAIN` | empty | Base domain for generated hostnames. Set it unless every container has an `npm.host` label and TrueNAS discovery is off. |
| `NPM_DEFAULT_SCHEME` | `http` | Forward scheme when `npm.scheme` is not set |
| `NPM_DEFAULT_CERT_NAME` | empty | Name of an existing NPM certificate (matched against its domain names or its nice name) to assign to created and updated hosts, which then also force SSL and enable HTTP/2 |
| `NPM_NETWORK` | empty | Docker network shared with NPM; containers on it are forwarded by name instead of IP |
| `NPM_DELETE_ORPHANS` | `false` | `true` deletes managed hosts whose service is gone during a sync |
| `NPM_SYNC_INTERVAL` | `60` | Seconds between syncs |
| `TRUENAS_URL` | empty | TrueNAS base URL. Discovery runs when this and `TRUENAS_API_KEY` are set. TLS certificates are not verified for this request. |
| `TRUENAS_API_KEY` | empty | TrueNAS API key |
| `TRUENAS_SKIP_APPS` | `glances` | Comma-separated app names to ignore |
| `PIHOLE_URL` | empty | Pi-hole base URL. DNS sync runs when this and `PIHOLE_PASSWORD` are set. |
| `PIHOLE_PASSWORD` | empty | Pi-hole password |
| `NPM_IP` | empty | Address the Pi-hole records point at; set it when DNS sync is on |

`NPM_REMOTE_CONFIG` (default `/config/remote-hosts.json`) is also read, but only by the static-file source in `nginx_proxy_sync/discovery/remote.py`, which the entry point does not enable.

## Running with Docker

The service needs the Docker socket and network access to NPM. [examples/docker-compose.yml](examples/docker-compose.yml) runs it next to NPM and a sample `whoami` container:

```sh
cp examples/.env.example examples/.env   # then fill in the NPM account
docker compose -f examples/docker-compose.yml up -d --build
```

To build the image on its own:

```sh
docker build -t nginx-proxy-sync .
```

Mount a volume at `/data` to keep the start-up backups.

## Development

Requires Python 3.12 or newer.

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

ruff format --check .
ruff check .
pytest
```

The tests replace the NPM, Pi-hole and Docker clients with fakes, so they need neither a network nor a Docker daemon. CI runs the same three commands plus a Docker build on every push and pull request.

```
nginx_proxy_sync/
├── __main__.py     entry point: start-up, periodic sync, event loop
├── config.py       environment variables
├── models.py       ProxyTarget dataclass
├── sync.py         reconciliation engine
├── clients/        NPM and Pi-hole API clients
└── discovery/      Docker, TrueNAS and static-file sources
tests/
examples/
```

## License

[MIT](LICENSE)
