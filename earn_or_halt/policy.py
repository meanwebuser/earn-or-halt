from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Any


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    available_cents: int
    margin_percent: float | None

    @property
    def should_halt(self) -> bool:
        return self.action == "halt"


@dataclass(frozen=True)
class EconomicPolicy:
    starting_credit_cents: int = 100
    grace_jobs: int = 3
    minimum_margin_percent: float = 20.0
    daily_cost_cap_cents: int = 500
    maximum_consecutive_failures: int = 5
    maximum_idle_cycles: int = 0
    halt_on_no_funds: bool = True

    def evaluate(
        self,
        stats: Mapping[str, Any],
        *,
        next_cost_cents: int = 0,
        external_halt_reason: str | None = None,
        idle_cycles: int = 0,
    ) -> Decision:
        revenue = int(stats.get("revenue_cents", 0))
        cost = int(stats.get("cost_cents", 0))
        daily_cost = int(stats.get("daily_cost_cents", 0))
        succeeded = int(stats.get("succeeded_jobs", 0))
        failures = int(stats.get("consecutive_failures", 0))
        available = self.starting_credit_cents + revenue - cost
        margin = None if revenue <= 0 else ((revenue - cost) / revenue) * 100.0

        if external_halt_reason:
            return Decision("halt", external_halt_reason, available, margin)

        if self.maximum_consecutive_failures and failures >= self.maximum_consecutive_failures:
            return Decision(
                "halt",
                f"consecutive failures reached {failures}",
                available,
                margin,
            )

        if self.daily_cost_cap_cents and daily_cost + next_cost_cents > self.daily_cost_cap_cents:
            return Decision(
                "halt",
                "daily cost cap would be exceeded",
                available,
                margin,
            )

        if self.halt_on_no_funds and next_cost_cents > available:
            return Decision(
                "halt",
                f"insufficient economic credit: {available} cents available",
                available,
                margin,
            )

        if succeeded >= self.grace_jobs:
            if revenue <= 0:
                return Decision("halt", "grace period ended without revenue", available, margin)
            if margin is not None and margin < self.minimum_margin_percent:
                return Decision(
                    "halt",
                    f"margin {margin:.2f}% is below {self.minimum_margin_percent:.2f}%",
                    available,
                    margin,
                )

        if self.maximum_idle_cycles and idle_cycles >= self.maximum_idle_cycles:
            return Decision(
                "halt",
                f"idle cycle limit reached ({idle_cycles})",
                available,
                margin,
            )

        return Decision("continue", "economics acceptable", available, margin)
