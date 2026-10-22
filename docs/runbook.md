# Runbook

What each alert means, how to confirm it, and what to do. Written to be followed
at the moment something is broken, so it stays short.

## First moves

```bash
ssh kota@server
cd ~/monitoring
docker compose ps                    # is the monitoring stack itself healthy?
curl -s localhost:9091/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health}'
docker exec monitoring-alert-sink wget -qO- http://127.0.0.1:8080/alerts | jq '.alerts[0:5]'
```

If the monitoring stack is down, everything is "down" — fix that first, then
trust the alerts.

## Alerts

### InstanceDown (critical)

Prometheus cannot scrape a target for two minutes. The service is down, the
container was removed, or the network between containers broke.

1. `docker ps` — is the container running?
2. `docker logs <container> --tail 50`.
3. If it exited: `docker compose up -d <service>` in its compose directory, then
   watch the logs for the reason it died.

### ProbeFailing (critical)

An HTTP probe failed for two minutes. The service is up but not serving.

1. `curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:<port>/` on the host.
2. If that works but the probe fails, it is a Host-header or container-network
   problem — check what the probe sends:
   `docker exec monitoring-blackbox wget -qS -O /dev/null <target>`.
3. 502/503 means the reverse proxy is up and the app behind it is not.

### HostDiskSpaceLow (warning) / HostDiskFillingUp (warning)

Below 15% free, or projected to fill within 24 hours.

1. `df -h` to confirm the mountpoint.
2. `du -xh --max-depth=1 /path | sort -h | tail` to find the consumer.
3. For media volumes, delete through the application (Radarr/Sonarr) so the
   library database stays consistent rather than deleting files behind it.
4. Do not delete Docker volumes unless you know what they hold:
   `docker system df -v` first.

**Known current state:** `/mnt/media` sits around 13% free, so this alert is
expected. Clear space or raise the threshold deliberately; do not silence it.

### HostMemoryPressure (warning)

Above 90% for ten minutes. The kernel starts reclaiming cache, then OOM-kills.

1. `free -h`, then `docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}' | sort -k2 -h`.
2. Look for the largest consumer that grew recently; restart it only after
   capturing why (`docker logs` and the OOM record in `dmesg`).
3. Long term: memory limits in each compose file, as this stack does.

### HostLoadHigh (warning)

Five-minute load above 1.5× core count for ten minutes.

1. `uptime`, then `top -b -n1 | head -15`.
2. Check whether it is CPU or I/O wait (`%wa`); I/O usually means a disk or
   network-backed mount, not a runaway process.

### ContainerStopped (warning)

cAdvisor has not seen a container for two minutes.

1. `docker ps -a --filter name=<name>` — stopped or missing?
2. `docker inspect <name> --format '{{.State.ExitCode}} {{.State.Error}}'`.
3. Exit code 137 is a kill (often OOM); 1 is an application error.

### ContainerRestartingLoop (warning)

More than one restart in fifteen minutes.

1. `docker inspect <name> --format '{{.RestartCount}}'`.
2. `docker logs <name> --tail 100` for the error before each exit.
3. Fix the cause; do not leave `restart: always` masking a crash loop.

### TaskQueueDown / TaskQueueBacklog / TaskQueueFailureRate

Only active once the task-queue target is enabled in `prometheus.yml`.

- **Down:** `curl -s localhost:8000/healthz` and `/readyz`; the readiness check
  names the failing dependency (database or broker).
- **Backlog above 50 for five minutes:** `docker compose ps` for workers, then
  `docker logs <worker>`; check that workers are claiming jobs and not stuck on a
  poison job.
- **Failure rate above 20%:** group failures by type and read the error on the
  job rows — a permanent failure will repeat until the payload or handler is
  fixed.

### Watchdog (none)

Always firing. Its only job is to prove the delivery path works: if
`alert-sink` stops receiving it, the pipeline is broken while everything else
looks quiet.

## Proving recovery

After fixing something, confirm the alert resolves rather than assuming:

```bash
curl -s localhost:9093/api/v2/alerts | jq '.[] | {name: .labels.alertname, state: .status.state}'
docker exec monitoring-alert-sink wget -qO- http://127.0.0.1:8080/alerts | jq '.alerts[] | select(.status=="resolved")'
```

A resolved notification in the sink is the evidence; a green dashboard is not.
