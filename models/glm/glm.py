from __future__ import annotations

from typing import Any

from ..base import BaseModel, SolveResult
from ..common import (
    SYSTEM_PROMPT,
    ensure_text_only_request,
    env,
    error_result,
    require_env,
    safe_dict,
    timed,
)
from ..pricing import estimate_cost
from ..telemetry import sanitized_base_url
from .versions import DEFAULT as DEFAULT_VERSION


ZAI_DEFAULT_BASE_URL = "https://api.z.ai/api/paas/v4/"
ZAI_DEFAULT_THINKING = "enabled"
ZAI_DEFAULT_REASONING_EFFORT = "max"
ZAI_DEFAULT_TIMEOUT_SECONDS = 3600.0
ZAI_REASONING_EFFORT_MODELS = {"glm-5.2"}


def optional_nonnegative_int_env(name: str) -> int | None:
    value = env(name)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def positive_float_env(name: str, default: float) -> float:
    value = env(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def usage_value(usage: Any, *names: str) -> int:
    for name in names:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        if value not in {None, ""}:
            return int(value or 0)
    return 0


def usage_detail_value(usage: Any, detail_name: str, *names: str) -> int | None:
    detail = usage.get(detail_name) if isinstance(usage, dict) else getattr(usage, detail_name, None)
    for name in names:
        value = detail.get(name) if isinstance(detail, dict) else getattr(detail, name, None)
        if value not in {None, ""}:
            return int(value or 0)
    return None


def first_choice(response: Any) -> Any:
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    if not choices:
        return None
    return choices[0]


def first_choice_message(response: Any) -> Any:
    choice = first_choice(response)
    if choice is None:
        return None
    return choice.get("message") if isinstance(choice, dict) else getattr(choice, "message", None)


def choice_finish_reason(raw_response: dict[str, Any]) -> str | None:
    choices = raw_response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        value = choices[0].get("finish_reason") or choices[0].get("finishReason")
        return str(value) if value else None
    return raw_response.get("finish_reason") or raw_response.get("status")


class GLMModel(BaseModel):
    def __init__(
        self,
        model: str | None = None,
        *,
        reasoning_budget_tokens: int | None = None,
        max_final_tokens: int | None = None,
    ) -> None:
        self._model = model or env("ZAI_MODEL", DEFAULT_VERSION)
        self._reasoning_budget_tokens = reasoning_budget_tokens
        self._max_final_tokens = max_final_tokens

    @property
    def model_id(self) -> str:
        return self._model

    def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult:
        request_payload: dict[str, Any] = {}
        raw_response: dict[str, Any] = {}
        latency_ms = 0
        try:
            api_key = require_env("ZAI_API_KEY")
            from openai import OpenAI

            base_url = env("ZAI_BASE_URL", ZAI_DEFAULT_BASE_URL) or ZAI_DEFAULT_BASE_URL
            timeout_seconds = positive_float_env("ZAI_TIMEOUT_SECONDS", ZAI_DEFAULT_TIMEOUT_SECONDS)
            max_retries = optional_nonnegative_int_env("ZAI_MAX_RETRIES")
            client_kwargs: dict[str, Any] = {
                "api_key": api_key,
                "base_url": base_url,
                "timeout": timeout_seconds,
            }
            if max_retries is not None:
                client_kwargs["max_retries"] = max_retries
            client = OpenAI(**client_kwargs)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": problem},
            ]
            kwargs: dict[str, Any] = {}
            if max_tokens is not None:
                kwargs["max_tokens"] = int(max_tokens)
            elif self._max_final_tokens is not None:
                kwargs["max_tokens"] = int(self._max_final_tokens)
            elif env("ZAI_MAX_TOKENS") is not None:
                kwargs["max_tokens"] = int(env("ZAI_MAX_TOKENS", "4096") or "4096")
            if env("ZAI_TEMPERATURE") is not None:
                kwargs["temperature"] = float(env("ZAI_TEMPERATURE", "0.2") or "0.2")

            extra_body: dict[str, Any] = {}
            thinking = env("ZAI_THINKING", ZAI_DEFAULT_THINKING) or ZAI_DEFAULT_THINKING
            if thinking:
                extra_body["thinking"] = {"type": thinking}
            if self.model_id in ZAI_REASONING_EFFORT_MODELS:
                extra_body["reasoning_effort"] = env("ZAI_REASONING_EFFORT", ZAI_DEFAULT_REASONING_EFFORT) or ZAI_DEFAULT_REASONING_EFFORT
            if extra_body:
                kwargs["extra_body"] = extra_body

            request_payload = {
                "endpoint": sanitized_base_url(f"{base_url.rstrip('/')}/chat/completions"),
                "model": self.model_id,
                "messages": messages,
                "stream": False,
                "timeout_seconds": timeout_seconds,
                "max_retries": max_retries,
                **{key: value for key, value in kwargs.items() if key != "extra_body"},
                **extra_body,
            }
            ensure_text_only_request(request_payload)

            response, latency_ms = timed(
                lambda: client.chat.completions.create(
                    model=self.model_id,
                    messages=messages,
                    **kwargs,
                )
            )
            raw_response = safe_dict(response)
            usage = getattr(response, "usage", None) or raw_response.get("usage") or {}
            prompt_tokens = usage_value(usage, "prompt_tokens", "input_tokens")
            completion_tokens = usage_value(usage, "completion_tokens", "output_tokens")
            total_tokens = usage_value(usage, "total_tokens")
            reasoning_tokens = usage_detail_value(usage, "completion_tokens_details", "reasoning_tokens") or usage_detail_value(usage, "output_tokens_details", "reasoning_tokens") or usage_value(usage, "reasoning_tokens") or None
            cached_input_tokens = usage_detail_value(usage, "prompt_tokens_details", "cached_tokens", "cached_input_tokens") or usage_detail_value(usage, "input_tokens_details", "cached_tokens", "cached_input_tokens") or usage_value(usage, "cached_input_tokens") or None
            message = first_choice_message(response)
            answer = (message.get("content") if isinstance(message, dict) else getattr(message, "content", "")) or ""
            reasoning_content = message.get("reasoning_content") if isinstance(message, dict) else getattr(message, "reasoning_content", None)
            if reasoning_content:
                raw_response["reasoning_content"] = reasoning_content
            cost = estimate_cost(
                "zai",
                self.model_id,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                cached_input_tokens=cached_input_tokens,
            )

            return SolveResult(
                model=self.model_id,
                answer=answer,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost.get("total") or 0.0,
                latency_ms=latency_ms,
                raw_response=raw_response,
                provider="zai",
                requested_model_id=self.model_id,
                resolved_model_id=raw_response.get("model") or self.model_id,
                request=request_payload,
                usage={
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": total_tokens or prompt_tokens + completion_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "cached_input_tokens": cached_input_tokens,
                    "cache_creation_input_tokens": None,
                    "raw": safe_dict(usage),
                    "source": "provider_response" if usage else "legacy_fields",
                },
                cost={**cost, "reasoning": None},
                finish_reason=choice_finish_reason(raw_response),
                response_id=raw_response.get("id"),
                provider_timestamp=raw_response.get("created"),
            )
        except Exception as exc:
            result = error_result(self.model_id, exc, latency_ms=latency_ms)
            result.provider = "zai"
            result.requested_model_id = self.model_id
            result.resolved_model_id = raw_response.get("model") or self.model_id
            result.request = request_payload or None
            result.raw_response = raw_response
            return result
