# Nginx Proxy Sync

Auto-discovers services and manages [Nginx Proxy Manager](https://github.com/NginxProxyManager/nginx-proxy-manager) proxy hosts. Supports multiple discovery sources, periodic reconciliation, and optional Pi-hole DNS sync.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Docker Labels](#docker-labels)
- [Environment Variables](#environment-variables)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)

## Features

- **Docker discovery:** Detects containers with `npm.enable: "true"` label and creates proxy hosts automatically
- **TrueNAS discovery:** Finds running apps via the TrueNAS API
- **Static hosts:** Loads additional targets from a JSON config file
- **CRUD:** Creates, updates, and deletes proxy hosts as services come and go
- **Periodic sync:** Reconciles desired state on an interval, catching drift from manual changes or restarts
- **Event-driven:** Reacts to Docker container start/stop events in real time
- **Orphan cleanup:** *Optionally* removes managed proxy hosts whose source has disappeared
- **Pi-hole DNS sync:** Automatically manages local DNS A records pointing to your NPM instance
- **Wildcard SSL:** Assigns an existing wildcard certificate to all managed hosts
- **Backup:** Snapshots all proxy hosts to JSON before each sync

## Quick Start

Sample compose setup.

```yaml
services:
  nginx-proxy-sync:
    build: .
    environment:
      NPM_URL: http://npm:81
      NPM_EMAIL: ${NPM_EMAIL}
      NPM_PASSWORD: ${NPM_PASSWORD}
      NPM_DOMAIN: ${NPM_DOMAIN}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./data:/data
    restart: unless-stopped
```

See [examples/](examples/) for a full compose setup and environment variable reference.

## Docker Labels

Add these labels to any container you want proxied:

```yaml
labels:
  # Required (allows detection)
  npm.enable: "true"

  # Optional overrides
  npm.host: "app.example.com"
  npm.port: "8080"
  npm.scheme: "https"
  npm.forward_host: "10.0.0.5"
```

If `npm.host` is not set, the domain defaults to `<container_name>.<NPM_DOMAIN>`.

If `npm.port` is not set, the assistant auto-detects the exposed port (skipping 22 and 443).

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `NPM_URL` | Yes | - | NPM API URL |
| `NPM_EMAIL` | Yes | - | NPM admin email |
| `NPM_PASSWORD` | Yes | - | NPM admin password |
| `NPM_DOMAIN` | No | `""` | Base domain for auto-generated hostnames |
| `NPM_DEFAULT_CERT_NAME` | No | `""` | Wildcard cert name to assign to hosts |
| `NPM_DEFAULT_SCHEME` | No | `http` | Default forward scheme |
| `NPM_DELETE_ORPHANS` | No | `false` | Delete managed hosts whose source is gone |
| `NPM_SYNC_INTERVAL` | No | `60` | Seconds between periodic syncs |
| `TRUENAS_URL` | No | `""` | TrueNAS API URL (enables TrueNAS discovery) |
| `TRUENAS_API_KEY` | No | `""` | TrueNAS API key |
| `TRUENAS_SKIP_APPS` | No | `glances` | Comma-separated app names to skip |
| `PIHOLE_URL` | No | `""` | Pi-hole API URL (enables DNS sync) |
| `PIHOLE_PASSWORD` | No | `""` | Pi-hole admin password |
| `NPM_IP` | No | `""` | IP address of NPM for Pi-hole DNS records |
| `NPM_REMOTE_CONFIG` | No | `/config/remote-hosts.json` | Path to static hosts JSON |

## How It Works

1. On startup, authenticates with NPM and backs up existing proxy hosts
2. Runs an initial sync - merges all discovery sources into a desired state and reconciles with NPM
3. Starts a periodic sync thread (default: every 60s)
4. Watches Docker events for real-time container start/stop handling

Managed hosts are tagged with a marker (`# managed-by:nginx-proxy-sync`) in the NPM advanced config field. The tool never modifies hosts it didn't create.

## Project Structure

```
nginx-proxy-sync/
├── main.py              # entry point
├── config.py            # environment variable loading
├── models.py            # ProxyTarget dataclass
├── sync.py              # reconciliation engine
├── clients/
│   ├── npm.py           # NPM API client
│   └── pihole.py        # Pi-hole DNS client
├── discovery/
│   ├── base.py          # DiscoverySource ABC
│   ├── docker.py        # Docker container discovery
│   ├── truenas.py       # TrueNAS app discovery
│   └── remote.py        # Static JSON file discovery
└── examples/
    ├── .env.example     # environment variable reference
    └── docker-compose.yml
```
