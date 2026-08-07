from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .util import env_bool, env_float, env_int


@dataclass(frozen=True)
class Config:
    data_dir: Path
    host: str
    port: int
    api_token: str | None
    provider: str
    llm_base_url: str
    llm_api_key: str | None
    primary_model: str
    fallback_base_url: str | None
    fallback_api_key: str | None
    fallback_model: str | None
    request_timeout_seconds: int
    scrape_company_sites: bool
    allow_http_company_urls: bool
    provider_cost_cents: int
    failure_cost_cents: int
    poll_interval_seconds: float
    generate_wait_seconds: int
    starting_credit_cents: int
    grace_jobs: int
    minimum_margin_percent: float
    daily_cost_cap_cents: int
    maximum_consecutive_failures: int
    maximum_idle_cycles: int
    halt_on_no_funds: bool
    body_limit_bytes: int

    @classmethod
    def from_env(cls) -> "Config":
        data_dir = Path(os.getenv("EOH_DATA_DIR", "./data")).expanduser().resolve()
        return cls(
            data_dir=data_dir,
            host=os.getenv("EOH_HOST", "0.0.0.0"),
            port=env_int("EOH_PORT", 8787, minimum=1),
            api_token=os.getenv("EOH_API_TOKEN") or None,
            provider=os.getenv("EOH_PROVIDER", "mock").strip().lower(),
            llm_base_url=os.getenv("EOH_LLM_BASE_URL", "https://api.openai.com/v1"),
            llm_api_key=os.getenv("EOH_LLM_API_KEY") or None,
            primary_model=os.getenv("EOH_PRIMARY_MODEL", "model-name"),
            fallback_base_url=os.getenv("EOH_FALLBACK_BASE_URL") or None,
            fallback_api_key=os.getenv("EOH_FALLBACK_API_KEY") or None,
            fallback_model=os.getenv("EOH_FALLBACK_MODEL") or None,
            request_timeout_seconds=env_int("EOH_REQUEST_TIMEOUT_SECONDS", 45, minimum=1),
            scrape_company_sites=env_bool("EOH_SCRAPE_COMPANY_SITES", False),
            allow_http_company_urls=env_bool("EOH_ALLOW_HTTP_COMPANY_URLS", False),
            provider_cost_cents=env_int("EOH_PROVIDER_COST_CENTS", 1, minimum=0),
            failure_cost_cents=env_int("EOH_FAILURE_COST_CENTS", 0, minimum=0),
            poll_interval_seconds=env_float("EOH_POLL_INTERVAL_SECONDS", 1.0, minimum=0.05),
            generate_wait_seconds=env_int("EOH_GENERATE_WAIT_SECONDS", 20, minimum=0),
            starting_credit_cents=env_int("EOH_STARTING_CREDIT_CENTS", 100, minimum=0),
            grace_jobs=env_int("EOH_GRACE_JOBS", 3, minimum=0),
            minimum_margin_percent=env_float("EOH_MINIMUM_MARGIN_PERCENT", 20.0),
            daily_cost_cap_cents=env_int("EOH_DAILY_COST_CAP_CENTS", 500, minimum=0),
            maximum_consecutive_failures=env_int(
                "EOH_MAXIMUM_CONSECUTIVE_FAILURES", 5, minimum=0
            ),
            maximum_idle_cycles=env_int("EOH_MAXIMUM_IDLE_CYCLES", 0, minimum=0),
            halt_on_no_funds=env_bool("EOH_HALT_ON_NO_FUNDS", True),
            body_limit_bytes=env_int("EOH_BODY_LIMIT_BYTES", 65_536, minimum=1),
        )
