# Infrastructure monitoring and alerting

Prometheus, Grafana, Alertmanager and exporters for a self-hosted Linux server
and the containers on it. Deployed and running: seven containers, five rule
groups, three provisioned dashboards, alerts delivered to an endpoint that
records what it receives.

This is project 2 of a three-project portfolio; the first is
[distributed-task-queue](../distributed-task-queue), which exposes the
application metrics these rules watch for.

## What it does

| Area | Implementation |
| --- | --- |
| Host metrics | `node_exporter` — CPU, memory, filesystem, load, network, systemd units |
| Container metrics | `cAdvisor` — per-container CPU, memory working set, restart tracking |
| Service availability | `blackbox_exporter` HTTP probes of the services published on the host |
| Application metrics | `/metrics` on the task queue API (submission, claim, retry, completion counters, queue depth from the database) |
| Alerting | 13 rules across host, containers, availability, task queue and a deliberate Watchdog |
| Delivery | Alertmanager → webhook → `alert-sink`, which records every notification it receives |
| Dashboards | Host overview, container overview, availability and alerts — provisioned from this repo, not clicked together |

## Layout

```
docker-compose.yml            seven services, memory-limited
prometheus/prometheus.yml     scrape config (add probe targets here)
prometheus/rules/*.yml        alert rules, versioned
alertmanager/alertmanager.yml routing and delivery
blackbox/blackbox.yml         probe modules
grafana/provisioning/         datasource + dashboard provider
grafana/dashboards/*.json     the three dashboards
alert-sink/                   tiny stdlib receiver, so delivery is provable
deploy.sh                     tar + ssh + docker compose up
docs/runbook.md               what each alert means and what to do about it
```

## Deploy

```bash
cp .env.example .env          # set GRAFANA_ADMIN_PASSWORD
./deploy.sh                   # REMOTE=kota@server by default, target ~/monitoring
```

Or by hand:

```bash
ssh kota@server 'mkdir -p ~/monitoring'
tar czf - --exclude=.git --exclude=.env . | ssh kota@server 'tar xzf - -C ~/monitoring'
ssh kota@server 'cd ~/monitoring && printf "GRAFANA_ADMIN_PASSWORD=..." > .env && docker compose up -d --build'
```

Ports: Prometheus `9091`, Grafana `3003`, Alertmanager `9093`. Everything else is
internal to the compose network — exporters are not published.

## Verified on the server

Checked after deployment, not assumed:

```
7 scrape targets, 7 up
5 rule groups: host (5), containers (2), availability (2), taskqueue (3), meta (1)
probe_success = 1 for all three probed services
Grafana 11.3.0, dashboards: host-overview, containers-overview, availability
Watchdog firing continuously and present in alert-sink output (pipeline proven)
HostDiskSpaceLow firing for /mnt/media at 13.3% free
```

## Design decisions

- **Memory limits on every container.** The host runs a media stack; monitoring
  must not be the reason it falls over. Prometheus is capped at 512 MB, Grafana
  at 320 MB, cAdvisor at 192 MB.
- **The alert receiver is a container.** Without it, "alerts work" is unproven
  until something real breaks. `alert-sink` accepts the webhook and exposes what
  it received at `/alerts`, so delivery can be checked at any time.
- **A permanently firing Watchdog.** Silence is indistinguishable from a broken
  pipeline; a guaranteed alert every 24 hours proves the path end to end.
- **Probe halves are split by Host header.** Next.js answers `400` to a request
  whose Host is `host.docker.internal`, so that target uses a module with an
  explicit `Host: localhost:3001`. Verified by asking the container directly.
- **The task-queue scrape target is commented out**, not left failing. An
  always-firing `TaskQueueDown` would train you to ignore it. Uncomment it when
  the API is deployed on `host.docker.internal:8000`.
- **Alerts exclude each other's causes.** `InstanceDown` ignores probe jobs
  (`ProbeFailing` covers them) and the task queue (which has its own alert), so
  one dead endpoint does not page four times.

## Limitations

- The task queue is not deployed on the server yet, so its three rules are
  loaded but idle. Enabling them is a two-line change in `prometheus.yml`.
- Alertmanager delivers to the local sink only. Pointing it at email or a chat
  webhook is a `receivers:` change in `alertmanager.yml`.
- Grafana dashboards are provisioned read-only (`allowUiUpdates: false`); edit
  the JSON in this repo rather than the UI.
