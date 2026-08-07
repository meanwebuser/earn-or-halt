from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .config import Config


@dataclass(frozen=True)
class GenerationResult:
    output: dict[str, Any]
    provider: str
    model: str
    cost_cents: int


class Provider(Protocol):
    estimated_cost_cents: int

    def generate(self, payload: dict[str, Any], context: dict[str, str]) -> GenerationResult:
        ...


def _clean(value: Any, limit: int = 1000) -> str:
    return " ".join(str(value or "").split())[:limit]


def build_prompt(payload: dict[str, Any], context: dict[str, str]) -> str:
    recipient_name = _clean(payload.get("recipient_name"), 200) or "there"
    recipient_title = _clean(payload.get("recipient_title"), 200)
    company = _clean(payload.get("company"), 300)
    icp = _clean(payload.get("icp"), 800)
    tone = _clean(payload.get("tone"), 200) or "direct, professional"
    offer = _clean(payload.get("offer"), 1200)
    site_context = "\n".join(f"- {key}: {_clean(value, 800)}" for key, value in context.items())
    if not site_context:
        site_context = "- no website context supplied"

    return f"""You draft lawful one-to-one B2B outreach. Do not invent facts and do not claim prior contact.
Return JSON only, with this exact shape:
{{"variants":[{{"subject":"...","body":"..."}},{{"subject":"...","body":"..."}},{{"subject":"...","body":"..."}}]}}
Each body must be at most 80 words and include a low-pressure call to action.

Recipient name: {recipient_name}
Recipient title: {recipient_title}
Company: {company}
Ideal customer profile: {icp}
Tone: {tone}
Offer: {offer}
Website context:
{site_context}
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("model did not return a JSON object")
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model response is not a JSON object")
    variants = value.get("variants")
    if not isinstance(variants, list) or len(variants) < 1:
        raise ValueError("model response has no variants")
    cleaned: list[dict[str, str]] = []
    for variant in variants[:3]:
        if not isinstance(variant, dict):
            continue
        subject = _clean(variant.get("subject"), 200)
        body = _clean(variant.get("body"), 2000)
        if body:
            cleaned.append({"subject": subject, "body": body})
    if not cleaned:
        raise ValueError("model response variants are empty")
    return {"variants": cleaned}


class MockProvider:
    def __init__(self, cost_cents: int):
        self.estimated_cost_cents = cost_cents

    def generate(self, payload: dict[str, Any], context: dict[str, str]) -> GenerationResult:
        name = _clean(payload.get("recipient_name"), 80) or "Здравствуйте"
        company = _clean(payload.get("company"), 120) or "вашей компании"
        offer = _clean(payload.get("offer"), 220) or "сократить ручную работу с помощью ИИ"
        context_hint = _clean(context.get("title") or context.get("h1"), 120)
        suffix = f" Увидел: {context_hint}." if context_hint else ""
        variants = [
            {
                "subject": f"Идея для {company}",
                "body": f"{name}, добрый день. Есть конкретная идея, как {offer}.{suffix} Могу прислать короткий разбор на одной странице без созвона — актуально?",
            },
            {
                "subject": "Короткий вопрос",
                "body": f"{name}, изучаю задачи команд, похожих на {company}. Мы помогаем {offer} без долгого внедрения.{suffix} Есть смысл показать рабочий пример на ваших вводных?",
            },
            {
                "subject": f"Черновик решения для {company}",
                "body": f"{name}, подготовил быструю гипотезу для {company}: {offer}.{suffix} Если направление релевантно, отправлю схему и оценку трудозатрат прямо письмом.",
            },
        ]
        return GenerationResult(
            output={"variants": variants},
            provider="mock",
            model="deterministic-demo",
            cost_cents=self.estimated_cost_cents,
        )


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        cost_cents: int,
        label: str,
    ):
        if not api_key:
            raise ValueError(f"API key is required for {label}")
        self.endpoint = self._chat_endpoint(base_url)
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.estimated_cost_cents = cost_cents
        self.label = label

    @staticmethod
    def _chat_endpoint(base_url: str) -> str:
        base = base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def generate(self, payload: dict[str, Any], context: dict[str, str]) -> GenerationResult:
        request_body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": build_prompt(payload, context)}],
                "temperature": 0.4,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=request_body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "EarnOrHalt/0.1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(2_000_000)
        except urllib.error.HTTPError as error:
            detail = error.read(4096).decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.label} returned HTTP {error.code}: {detail}") from error
        value = json.loads(raw.decode("utf-8"))
        try:
            text = value["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError(f"{self.label} returned an unexpected response") from error
        output = _extract_json_object(str(text))
        return GenerationResult(
            output=output,
            provider=self.label,
            model=self.model,
            cost_cents=self.estimated_cost_cents,
        )


class FallbackProvider:
    def __init__(self, primary: Provider, fallback: Provider | None):
        self.primary = primary
        self.fallback = fallback
        self.estimated_cost_cents = primary.estimated_cost_cents

    def generate(self, payload: dict[str, Any], context: dict[str, str]) -> GenerationResult:
        try:
            return self.primary.generate(payload, context)
        except Exception as primary_error:
            if self.fallback is None:
                raise
            try:
                return self.fallback.generate(payload, context)
            except Exception as fallback_error:
                raise RuntimeError(
                    f"primary provider failed ({primary_error}); fallback failed ({fallback_error})"
                ) from fallback_error


def create_provider(config: Config) -> Provider:
    if config.provider == "mock":
        return MockProvider(config.provider_cost_cents)
    if config.provider not in {"openai", "openai-compatible"}:
        raise ValueError("EOH_PROVIDER must be 'mock' or 'openai-compatible'")
    primary = OpenAICompatibleProvider(
        base_url=config.llm_base_url,
        api_key=config.llm_api_key or "",
        model=config.primary_model,
        timeout_seconds=config.request_timeout_seconds,
        cost_cents=config.provider_cost_cents,
        label="primary",
    )
    fallback: Provider | None = None
    if config.fallback_model:
        fallback = OpenAICompatibleProvider(
            base_url=config.fallback_base_url or config.llm_base_url,
            api_key=config.fallback_api_key or config.llm_api_key or "",
            model=config.fallback_model,
            timeout_seconds=config.request_timeout_seconds,
            cost_cents=config.provider_cost_cents,
            label="fallback",
        )
    return FallbackProvider(primary, fallback)
