from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .util import utc_now


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed')),
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    price_cents INTEGER NOT NULL DEFAULT 0 CHECK(price_cents >= 0),
                    estimated_cost_cents INTEGER NOT NULL DEFAULT 0 CHECK(estimated_cost_cents >= 0),
                    actual_cost_cents INTEGER NOT NULL DEFAULT 0 CHECK(actual_cost_cents >= 0),
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0)
                );

                CREATE INDEX IF NOT EXISTS jobs_status_created_idx
                    ON jobs(status, created_at);

                CREATE TABLE IF NOT EXISTS ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('revenue','cost','credit','refund')),
                    amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
                    job_id TEXT,
                    note TEXT,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );

                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _job_from_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        value["payload"] = json.loads(value.pop("payload_json"))
        result_json = value.pop("result_json")
        value["result"] = json.loads(result_json) if result_json else None
        return value

    def enqueue_job(
        self,
        payload: dict[str, Any],
        *,
        price_cents: int,
        estimated_cost_cents: int,
    ) -> dict[str, Any]:
        if price_cents < 0 or estimated_cost_cents < 0:
            raise ValueError("price and estimated cost must be non-negative")
        job_id = uuid.uuid4().hex
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs(
                    id, created_at, updated_at, status, payload_json,
                    price_cents, estimated_cost_cents
                ) VALUES (?, ?, ?, 'queued', ?, ?, ?)
                """,
                (
                    job_id,
                    now,
                    now,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    price_cents,
                    estimated_cost_cents,
                ),
            )
        job = self.get_job(job_id)
        assert job is not None
        return job

    def claim_next_job(self) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at, id LIMIT 1"
            ).fetchone()
            if row is None:
                connection.execute("COMMIT")
                return None
            now = utc_now()
            connection.execute(
                """
                UPDATE jobs
                SET status='running', updated_at=?, attempts=attempts+1
                WHERE id=? AND status='queued'
                """,
                (now, row["id"]),
            )
            updated = connection.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
            connection.execute("COMMIT")
            return self._job_from_row(updated)
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    def complete_job(
        self,
        job_id: str,
        result: dict[str, Any],
        *,
        actual_cost_cents: int,
    ) -> None:
        if actual_cost_cents < 0:
            raise ValueError("actual cost must be non-negative")
        now = utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT price_cents FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            connection.execute(
                """
                UPDATE jobs
                SET status='succeeded', updated_at=?, result_json=?, error=NULL,
                    actual_cost_cents=?
                WHERE id=?
                """,
                (
                    now,
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    actual_cost_cents,
                    job_id,
                ),
            )
            if actual_cost_cents:
                connection.execute(
                    "INSERT INTO ledger(created_at, kind, amount_cents, job_id, note) VALUES (?, 'cost', ?, ?, ?)",
                    (now, actual_cost_cents, job_id, "provider cost"),
                )
            price_cents = int(row["price_cents"])
            if price_cents:
                connection.execute(
                    "INSERT INTO ledger(created_at, kind, amount_cents, job_id, note) VALUES (?, 'revenue', ?, ?, ?)",
                    (now, price_cents, job_id, "credited job revenue"),
                )
            connection.execute("COMMIT")
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    def fail_job(self, job_id: str, error: str, *, actual_cost_cents: int = 0) -> None:
        now = utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE jobs
                SET status='failed', updated_at=?, error=?, actual_cost_cents=?
                WHERE id=?
                """,
                (now, error[:4000], max(0, actual_cost_cents), job_id),
            )
            if actual_cost_cents:
                connection.execute(
                    "INSERT INTO ledger(created_at, kind, amount_cents, job_id, note) VALUES (?, 'cost', ?, ?, ?)",
                    (now, actual_cost_cents, job_id, "failed provider call"),
                )
            connection.execute("COMMIT")
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._job_from_row(row)

    def list_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 200))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._job_from_row(row) for row in rows if row is not None]

    def record_ledger(self, kind: str, amount_cents: int, note: str = "") -> None:
        if kind not in {"revenue", "cost", "credit", "refund"}:
            raise ValueError("unsupported ledger kind")
        if amount_cents < 0:
            raise ValueError("amount_cents must be non-negative")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO ledger(created_at, kind, amount_cents, note) VALUES (?, ?, ?, ?)",
                (utc_now(), kind, amount_cents, note[:1000]),
            )

    def stats(self) -> dict[str, int]:
        with self._connect() as connection:
            totals = {
                row["kind"]: int(row["total"] or 0)
                for row in connection.execute(
                    "SELECT kind, SUM(amount_cents) AS total FROM ledger GROUP BY kind"
                ).fetchall()
            }
            daily_cost = int(
                connection.execute(
                    """
                    SELECT COALESCE(SUM(amount_cents), 0)
                    FROM ledger
                    WHERE kind='cost' AND substr(created_at, 1, 10)=substr(?, 1, 10)
                    """,
                    (utc_now(),),
                ).fetchone()[0]
            )
            counts = {
                row["status"]: int(row["count"])
                for row in connection.execute(
                    "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
                ).fetchall()
            }
            recent = connection.execute(
                """
                SELECT status FROM jobs
                WHERE status IN ('succeeded','failed')
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()

        consecutive_failures = 0
        for row in recent:
            if row["status"] != "failed":
                break
            consecutive_failures += 1

        revenue = totals.get("revenue", 0) + totals.get("credit", 0)
        cost = totals.get("cost", 0)
        refunds = totals.get("refund", 0)
        revenue = max(0, revenue - refunds)
        return {
            "revenue_cents": revenue,
            "cost_cents": cost,
            "profit_cents": revenue - cost,
            "daily_cost_cents": daily_cost,
            "queued_jobs": counts.get("queued", 0),
            "running_jobs": counts.get("running", 0),
            "succeeded_jobs": counts.get("succeeded", 0),
            "failed_jobs": counts.get("failed", 0),
            "consecutive_failures": consecutive_failures,
        }

    def set_meta(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_meta(self, key: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def request_halt(self, reason: str) -> None:
        self.set_meta("halt_reason", reason[:1000] or "halt requested")

    def clear_halt(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM meta WHERE key='halt_reason'")

    def halt_reason(self) -> str | None:
        return self.get_meta("halt_reason")
