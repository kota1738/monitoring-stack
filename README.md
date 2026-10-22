# Infrastructure monitoring and alerting

**Status: in progress.** The specification is written and committed; the stack is
being built. Nothing below is implemented yet — this README will be rewritten
with real setup steps, committed dashboard JSON and measured alert timings as
each part lands.

## What this will do

Observability for a self-hosted Linux server and the containerised services on
it, and for the [task queue API](../distributed-task-queue) in particular:

- Host metrics — CPU, memory, disk usage, disk I/O, load average, uptime.
- Per-container CPU and memory, restart counts, containers that have died.
- HTTP probes of the task queue API's `/healthz` and `/readyz`, plus Postgres
  and Redis reachability.
- Application metrics from the service itself: queue depth, jobs by status,
  retry counts, worker claim latency, exposed on `/metrics`.
- Alert rules for host down, disk above 85%, failing probe, restarting
  container, queue depth and failure rate above threshold.
- Committed Grafana dashboards: host overview, container overview, task queue
  overview.
- Runbooks: what to do when each alert fires, and how the alert was proven to
  fire and resolve.

## Stack

Prometheus · Grafana · Alertmanager · node_exporter · cAdvisor · Docker Compose ·
Python (custom exporter) · Linux

## Plan

The full specification, feature table and acceptance criteria live in
[`docs/spec.md`](docs/spec.md).

## Why it exists

A service is not finished until someone can tell whether it is healthy. This
project is the operational half of the backend work: the same system observed
properly, with alerts that fire for real conditions and runbooks that describe
recovery rather than guesses.
