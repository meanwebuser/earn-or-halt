from __future__ import annotations

import hmac
import json
import threading
import time
import urllib.parse
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import __version__
from .config import Config
from .storage import Storage
from .util import read_json, utc_now


@dataclass
class ServiceContext:
    config: Config
    storage: Storage
    state_path: Path
    stop_event: threading.Event


class EarnOrHaltHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], context: ServiceContext):
        self.context = context
        super().__init__(address, EarnOrHaltHandler)


class EarnOrHaltHandler(BaseHTTPRequestHandler):
    server: EarnOrHaltHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[http] {self.address_string()} {format % args}", flush=True)

    def _send_json(self, status: int, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _authorized(self) -> bool:
        token = self.server.context.config.api_token
        if not token:
            return True
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {token}"
        return hmac.compare_digest(supplied, expected)

    def _require_authorized(self) -> bool:
        if self._authorized():
            return True
        self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        return False

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required")
        length = int(raw_length)
        if length < 0 or length > self.server.context.config.body_limit_bytes:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length)
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    @staticmethod
    def _non_negative_int(value: Any, field: str, default: int) -> int:
        if value is None:
            return default
        if isinstance(value, bool):
            raise ValueError(f"{field} must be an integer")
        result = int(value)
        if result < 0:
            raise ValueError(f"{field} must be non-negative")
        return result

    def _enqueue(self, body: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "recipient_name",
            "recipient_title",
            "company",
            "company_url",
            "icp",
            "tone",
            "offer",
            "metadata",
        }
        payload = {key: body[key] for key in allowed if key in body}
        if not str(payload.get("company", "")).strip():
            raise ValueError("company is required")
        if not str(payload.get("offer", "")).strip():
            raise ValueError("offer is required")
        price = self._non_negative_int(body.get("price_cents"), "price_cents", 29)
        estimated = self._non_negative_int(
            body.get("estimated_cost_cents"),
            "estimated_cost_cents",
            self.server.context.config.provider_cost_cents,
        )
        return self.server.context.storage.enqueue_job(
            payload,
            price_cents=price,
            estimated_cost_cents=estimated,
        )

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/healthz":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "earn-or-halt",
                    "version": __version__,
                    "time": utc_now(),
                },
            )
            return
        if not self._require_authorized():
            return
        try:
            if parsed.path == "/v1/state":
                state = read_json(self.server.context.state_path, {}) or {}
                state["stats"] = self.server.context.storage.stats()
                self._send_json(HTTPStatus.OK, state)
                return
            if parsed.path == "/v1/jobs":
                query = urllib.parse.parse_qs(parsed.query)
                limit = int(query.get("limit", ["50"])[0])
                self._send_json(
                    HTTPStatus.OK,
                    {"jobs": self.server.context.storage.list_jobs(limit=limit)},
                )
                return
            if parsed.path.startswith("/v1/jobs/"):
                job_id = parsed.path.rsplit("/", 1)[-1]
                job = self.server.context.storage.get_job(job_id)
                if job is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "job not found"})
                else:
                    self._send_json(HTTPStatus.OK, job)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception as error:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if not self._require_authorized():
            return
        try:
            body = self._read_json()
            if parsed.path == "/v1/jobs":
                job = self._enqueue(body)
                self._send_json(HTTPStatus.ACCEPTED, job)
                return
            if parsed.path == "/v1/generate":
                job = self._enqueue(body)
                wait_seconds = self._non_negative_int(
                    body.get("wait_seconds"),
                    "wait_seconds",
                    self.server.context.config.generate_wait_seconds,
                )
                deadline = time.monotonic() + min(wait_seconds, 120)
                while time.monotonic() < deadline:
                    current = self.server.context.storage.get_job(job["id"])
                    if current and current["status"] in {"succeeded", "failed"}:
                        status = HTTPStatus.OK if current["status"] == "succeeded" else HTTPStatus.BAD_GATEWAY
                        self._send_json(status, current)
                        return
                    if self.server.context.stop_event.wait(0.1):
                        break
                current = self.server.context.storage.get_job(job["id"]) or job
                self._send_json(HTTPStatus.ACCEPTED, current)
                return
            if parsed.path == "/v1/ledger":
                kind = str(body.get("kind", ""))
                amount = self._non_negative_int(body.get("amount_cents"), "amount_cents", 0)
                note = str(body.get("note", ""))
                self.server.context.storage.record_ledger(kind, amount, note)
                self._send_json(HTTPStatus.CREATED, {"recorded": True})
                return
            if parsed.path == "/v1/halt":
                reason = str(body.get("reason", "operator halt"))
                self.server.context.storage.request_halt(reason)
                self._send_json(HTTPStatus.ACCEPTED, {"status": "halting", "reason": reason})
                return
            if parsed.path == "/v1/clear-halt":
                self.server.context.storage.clear_halt()
                self._send_json(HTTPStatus.OK, {"cleared": True})
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception as error:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
