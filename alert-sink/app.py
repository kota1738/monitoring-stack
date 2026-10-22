"""Alert receiver that posts to Discord.

Alertmanager posts to ``/alerts``. The sink records what arrived — so the
delivery path can be proved rather than assumed — and, when a Discord webhook is
configured, posts the same notification to a channel as an embed.

The webhook URL is a credential, so it lives in ``.env`` rather than in the
tracked Alertmanager config. A webhook is used rather than a gateway bot
because Alertmanager is push-based: nothing needs to receive commands, and a
gateway connection would be a second thing to keep alive for no gain.

    POST /alerts  -> record the notification, then post it to Discord
    GET  /alerts  -> everything received, newest first
    GET  /discord -> whether and where notifications are being sent (no secret)
    GET  /healthz -> liveness for the compose healthcheck

Standard library only, so the image needs no build step beyond copying this
file.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RECEIVED: list[dict] = []
LOCK = threading.Lock()
MAX_KEPT = 500

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
DISCORD_MENTION = os.environ.get("DISCORD_MENTION", "").strip()
DISCORD_USERNAME = os.environ.get("DISCORD_USERNAME", "server-monitoring").strip()

FIRING_COLOUR = 0xE74C3C
RESOLVED_COLOUR = 0x2ECC71


def discord_enabled() -> bool:
    return DISCORD_WEBHOOK_URL.startswith("https://discord.com/api/webhooks/")


def build_payload(payload: dict) -> dict:
    """One Discord message for the notification, one embed per alert."""
    alerts = payload.get("alerts", [])
    firing = sum(1 for a in alerts if a.get("status") == "firing")
    resolved = len(alerts) - firing
    label = payload.get("groupLabels", {}).get("alertname") or "alerts"

    embeds = []
    for alert in alerts[:10]:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        is_firing = alert.get("status") == "firing"
        embeds.append(
            {
                "title": f"{'FIRING' if is_firing else 'RESOLVED'} · {labels.get('alertname', 'alert')}",
                "colour": FIRING_COLOUR if is_firing else RESOLVED_COLOUR,
                "description": annotations.get("summary", ""),
                "fields": [
                    {"name": "Severity", "value": labels.get("severity", "n/a"), "inline": True},
                    {"name": "Instance", "value": labels.get("instance", "n/a"), "inline": True},
                    {"name": "Detail", "value": annotations.get("description", "—")[:1000]},
                ],
                "footer": {"text": f"started {alert.get('startsAt', 'unknown')}"},
            }
        )

    content = f"**{label}** — {firing} firing, {resolved} resolved"
    if firing and DISCORD_MENTION:
        content = f"{DISCORD_MENTION} {content}"

    return {"username": DISCORD_USERNAME, "content": content, "embeds": embeds}


def post_to_discord(payload: dict) -> tuple[bool, str | None]:
    """Return (delivered, error). Never raises: the webhook must still succeed."""
    if not discord_enabled():
        return False, "discord webhook not configured"
    body = json.dumps(build_payload(payload)).encode()
    request = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "alert-sink/1.2"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return 200 <= response.status < 300, None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        print(f"discord delivery failed: {exc.code} {detail}", flush=True)
        return False, f"{exc.code}: {detail}"
    except Exception as exc:  # noqa: BLE001 - report to caller, never raise
        print(f"discord delivery failed: {exc}", flush=True)
        return False, str(exc)


class Handler(BaseHTTPRequestHandler):
    server_version = "alert-sink/1.2"

    def _respond(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path.startswith("/healthz"):
            self._respond(200, {"status": "ok"})
            return
        if self.path.startswith("/discord"):
            self._respond(
                200,
                {
                    "enabled": discord_enabled(),
                    "username": DISCORD_USERNAME,
                    "mention": DISCORD_MENTION or None,
                    # Never echo the webhook URL itself: it is the credential.
                    "webhook_host": "discord.com" if discord_enabled() else None,
                },
            )
            return
        if self.path.startswith("/alerts"):
            with LOCK:
                self._respond(200, {"count": len(RECEIVED), "alerts": RECEIVED[::-1][:50]})
            return
        self._respond(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        if not self.path.startswith("/alerts"):
            self._respond(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._respond(400, {"error": "invalid json"})
            return

        delivered, error = post_to_discord(payload)
        received_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        for alert in payload.get("alerts", []):
            entry = {
                "received_at": received_at,
                "status": alert.get("status"),
                "name": alert.get("labels", {}).get("alertname"),
                "severity": alert.get("labels", {}).get("severity"),
                "instance": alert.get("labels", {}).get("instance"),
                "summary": alert.get("annotations", {}).get("summary"),
                "starts_at": alert.get("startsAt"),
                "ends_at": alert.get("endsAt"),
                "posted": delivered,
                "post_error": error,
            }
            with LOCK:
                RECEIVED.append(entry)
                del RECEIVED[:-MAX_KEPT]
            print(json.dumps(entry), flush=True)
        self._respond(200, {"accepted": len(payload.get("alerts", [])), "posted": delivered})

    def log_message(self, fmt: str, *args) -> None:  # quieter default logging
        if os.environ.get("SINK_VERBOSE") == "1":
            super().log_message(fmt, *args)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    state = "discord enabled" if discord_enabled() else "discord not configured"
    print(f"alert-sink listening on :{port} ({state})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
