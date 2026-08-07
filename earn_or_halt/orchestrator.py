from __future__ import annotations

import signal
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from . import __version__
from .config import Config
from .policy import Decision, EconomicPolicy
from .providers import Provider, create_provider
from .scraper import fetch_company_context
from .service import EarnOrHaltHTTPServer, ServiceContext
from .storage import Storage
from .util import atomic_write_json, utc_now


class Orchestrator:
    def __init__(self, config: Config):
        self.config = config
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage = Storage(self.config.data_dir / "earn-or-halt.sqlite3")
        self.provider: Provider = create_provider(config)
        self.policy = EconomicPolicy(
            starting_credit_cents=config.starting_credit_cents,
            grace_jobs=config.grace_jobs,
            minimum_margin_percent=config.minimum_margin_percent,
            daily_cost_cap_cents=config.daily_cost_cap_cents,
            maximum_consecutive_failures=config.maximum_consecutive_failures,
            maximum_idle_cycles=config.maximum_idle_cycles,
            halt_on_no_funds=config.halt_on_no_funds,
        )
        self.state_path = self.config.data_dir / "runtime-state.json"
        self.stop_event = threading.Event()
        self.idle_cycles = 0
        self.current_job_id: str | None = None
        context = ServiceContext(
            config=config,
            storage=self.storage,
            state_path=self.state_path,
            stop_event=self.stop_event,
        )
        self.server = EarnOrHaltHTTPServer((config.host, config.port), context)
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.2},
            name="earn-or-halt-http",
            daemon=True,
        )
        self.exit_reason = "normal shutdown"
        self.policy_halted = False

    def _state(self, status: str, decision: Decision | None = None) -> dict[str, Any]:
        stats = self.storage.stats()
        return {
            "schema": "earn-or-halt.runtime-state.v1",
            "service": "earn-or-halt",
            "version": __version__,
            "status": status,
            "updated_at": utc_now(),
            "current_job_id": self.current_job_id,
            "idle_cycles": self.idle_cycles,
            "decision": None
            if decision is None
            else {
                "action": decision.action,
                "reason": decision.reason,
                "available_cents": decision.available_cents,
                "margin_percent": decision.margin_percent,
            },
            "stats": stats,
        }

    def write_state(self, status: str, decision: Decision | None = None) -> None:
        atomic_write_json(self.state_path, self._state(status, decision))

    def stop(self, reason: str = "stop requested") -> None:
        if not self.stop_event.is_set():
            self.exit_reason = reason
            self.stop_event.set()

    def _evaluate(self, *, next_cost_cents: int = 0) -> Decision:
        return self.policy.evaluate(
            self.storage.stats(),
            next_cost_cents=next_cost_cents,
            external_halt_reason=self.storage.halt_reason(),
            idle_cycles=self.idle_cycles,
        )

    def _process_job(self, job: dict[str, Any]) -> None:
        payload = job["payload"]
        context: dict[str, str] = {}
        scrape_error: str | None = None
        company_url = str(payload.get("company_url", "")).strip()
        if self.config.scrape_company_sites and company_url:
            try:
                context = fetch_company_context(
                    company_url,
                    allow_http=self.config.allow_http_company_urls,
                    timeout_seconds=min(self.config.request_timeout_seconds, 10),
                )
            except Exception as error:
                scrape_error = str(error)

        result = self.provider.generate(payload, context)
        output = dict(result.output)
        output["provider"] = result.provider
        output["model"] = result.model
        if context:
            output["company_context"] = context
        if scrape_error:
            output["company_context_warning"] = scrape_error
        self.storage.complete_job(
            job["id"],
            output,
            actual_cost_cents=result.cost_cents,
        )

    def run(self) -> int:
        self.write_state("starting")
        self.server_thread.start()
        print(
            f"[earn-or-halt] API listening on http://{self.config.host}:{self.config.port}; "
            f"provider={self.config.provider}",
            flush=True,
        )
        try:
            while not self.stop_event.is_set():
                stats = self.storage.stats()
                if stats["queued_jobs"] <= 0:
                    self.idle_cycles += 1
                    decision = self._evaluate(next_cost_cents=0)
                    self.write_state("idle", decision)
                    if decision.should_halt:
                        self.policy_halted = True
                        self.storage.request_halt(decision.reason)
                        self.stop(f"policy halt: {decision.reason}")
                        break
                    self.stop_event.wait(self.config.poll_interval_seconds)
                    continue

                self.idle_cycles = 0
                decision = self._evaluate(next_cost_cents=self.provider.estimated_cost_cents)
                self.write_state("evaluating", decision)
                if decision.should_halt:
                    self.policy_halted = True
                    self.storage.request_halt(decision.reason)
                    self.stop(f"policy halt: {decision.reason}")
                    break

                job = self.storage.claim_next_job()
                if job is None:
                    continue
                self.current_job_id = job["id"]
                self.write_state("working", decision)
                try:
                    self._process_job(job)
                    print(f"[earn-or-halt] job {job['id']} succeeded", flush=True)
                except Exception as error:
                    self.storage.fail_job(
                        job["id"],
                        f"{type(error).__name__}: {error}",
                        actual_cost_cents=self.config.failure_cost_cents,
                    )
                    print(f"[earn-or-halt] job {job['id']} failed: {error}", flush=True)
                    traceback.print_exc()
                finally:
                    self.current_job_id = None
                    self.write_state("running", self._evaluate())
        finally:
            final_decision = self._evaluate()
            final_status = "halted" if self.policy_halted or self.storage.halt_reason() else "stopped"
            self.write_state(final_status, final_decision)
            self.server.shutdown()
            self.server.server_close()
            self.server_thread.join(timeout=3)
            print(f"[earn-or-halt] {self.exit_reason}", flush=True)
        return 20 if self.policy_halted else 0


def run(config: Config | None = None) -> int:
    config = config or Config.from_env()
    orchestrator = Orchestrator(config)

    def handle_signal(signum: int, _frame: Any) -> None:
        orchestrator.stop(f"signal {signum}")

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, handle_signal)
    return orchestrator.run()
