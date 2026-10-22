## Project 2 specification — infrastructure monitoring and alerting

**Purpose:** prove you can operate systems, not just build them. This is the
project that separates you from candidates who only have CRUD apps.

**Stack:** Prometheus, Grafana, Alertmanager, node_exporter, cAdvisor, Docker
Compose, Python (custom exporter). Runs on the Fedora homelab.

**Features**

| Area | Requirement |
| --- | --- |
| Host metrics | CPU, memory, disk usage, disk I/O, load average, uptime |
| Container metrics | Per-container CPU/memory, restart counts, container down |
| Service health | HTTP probe of the task queue API, its `/readyz`, Postgres and Redis |
| Application metrics | Job queue depth, jobs by status, retry counts, worker claim latency |
| Alerting | Rules for host down, disk > 85%, service probe failing, container restarting, queue depth above threshold, failure rate above threshold |
| Delivery | Alertmanager → email or generic webhook |
| Dashboards | Committed Grafana JSON: host overview, container overview, task queue overview |
| Docs | Install steps, how to add a scrape target, alert response runbook, recovery test |

**Implementation notes**

- Add `prometheus_client` to the task queue service and expose `/metrics`. Count
  job submissions, completions by status, attempts, and current queue depth from
  Postgres. This is the integration that makes the two projects one portfolio.
- Keep every scrape target in `prometheus/prometheus.yml`; no manual clicking.
- Alert rules live in `prometheus/rules/*.yml`, versioned with the repo.
- Add a `recovery.md` section: what you do when each alert fires, and how you
  proved it works (stop the service, watch the alert fire, restart, watch it
  resolve).

**Acceptance criteria**

- [ ] `docker compose up -d` from a clean clone gives a working dashboard.
- [ ] Stopping the API produces a firing alert within two minutes.
- [ ] Filling disk above the threshold (use a test file) produces a firing alert.
- [ ] Dashboard panels load with data and survive a restart.
- [ ] README documents setup, screenshots, alert table and recovery steps.
- [ ] No credentials in the repo; `.env.example` only.

**CV bullet you may use once it is true:** "Deployed a Prometheus, Grafana and
Alertmanager stack on Docker, collecting host, container and application metrics
for a Linux server and a Python service, with alert rules for service, disk and
queue health."
