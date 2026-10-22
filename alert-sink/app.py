"""Minimal alert receiver.

Alertmanager posts to ``/alerts``; this records what arrived so the delivery
path can be proved rather than assumed. Standard library only, so the image
needs no build step beyond copying this file.

    GET /alerts   -> everything received, newest first
    GET /healthz  -> liveness for the compose healthcheck
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RECEIVED: list[dict] = []
LOCK = threading.Lock()
MAX_KEPT = 500


class Handler(BaseHTTPRequestHandler):
    server_version = "alert-sink/1.0"

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
            }
            with LOCK:
                RECEIVED.append(entry)
                del RECEIVED[:-MAX_KEPT]
            print(json.dumps(entry), flush=True)
        self._respond(200, {"accepted": len(payload.get("alerts", []))})

    def log_message(self, fmt: str, *args) -> None:  # quieter default logging
        if os.environ.get("SINK_VERBOSE") == "1":
            super().log_message(fmt, *args)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"alert-sink listening on :{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
