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


XAI_DEFAULT_BASE_URL = "https://api.x.ai/v1"
XAI_DEFAULT_REASONING_EFFORT = "high"
XAI_DEFAULT_TIMEOUT_SECONDS = 3600.0
XAI_DEFAULT_MAX_OUTPUT_TOKENS_PER_REQUEST = 256_000
XAI_CONTINUATION_INPUT = "Continue the reasoning and provide the complete final answer."
XAI_CANONICAL_MODEL_ALIASES = {
    "grok-code-fast-1": "grok-build-0.1",
}
XAI_REASONING_MODELS = {"grok-4.3"}
XAI_REASONING_EFFORTS = {"none", "low", "medium", "high"}


def canonical_model_id(model_id: str) -> str:
    return XAI_CANONICAL_MODEL_ALIASES.get(model_id, model_id)


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


def provider_cost_ticks(raw_response: dict[str, Any]) -> int | None:
    value = raw_response.get("cost_in_usd_ticks")
    if value is None and isinstance(raw_response.get("usage"), dict):
        value = raw_response["usage"].get("cost_in_usd_ticks")
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str):
        return text
    parts: list[str] = []
    output = response.get("output", []) if isinstance(response, dict) else getattr(response, "output", [])
    for item in output or []:
        contents = item.get("content", []) if isinstance(item, dict) else getattr(item, "content", [])
        for content in contents or []:
            value = content.get("text") if isinstance(content, dict) else getattr(content, "text", None)
            if isinstance(value, str):
                parts.append(value)
    return "\n".join(parts)


def response_finish_reason(raw_response: dict[str, Any]) -> str | None:
    incomplete = raw_response.get("incomplete_details")
    if isinstance(incomplete, dict) and incomplete.get("reason"):
        return str(incomplete["reason"])
    status = raw_response.get("status")
    return str(status) if status else None


class GrokModel(BaseModel):
    def __init__(
        self,
        model: str | None = None,
        *,
        reasoning_budget_tokens: int | None = None,
        max_final_tokens: int | None = None,
    ) -> None:
        self._model = canonical_model_id(model or env("XAI_MODEL", DEFAULT_VERSION))
        self._reasoning_budget_tokens = reasoning_budget_tokens
        self._max_final_tokens = max_final_tokens

    @property
    def model_id(self) -> str:
        return self._model

    def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult:
        request_payload: dict[str, Any] = {}
        last_raw_response: dict[str, Any] = {}
        latency_ms = 0
        try:
            api_key = require_env("XAI_API_KEY")
            from openai import OpenAI

            base_url = env("XAI_BASE_URL", XAI_DEFAULT_BASE_URL) or XAI_DEFAULT_BASE_URL
            timeout_seconds = positive_float_env("XAI_TIMEOUT_SECONDS", XAI_DEFAULT_TIMEOUT_SECONDS)
            max_retries = optional_nonnegative_int_env("XAI_MAX_RETRIES")
            client_kwargs: dict[str, Any] = {
                "api_key": api_key,
                "base_url": base_url,
                "timeout": timeout_seconds,
            }
            if max_retries is not None:
                client_kwargs["max_retries"] = max_retries
            client = OpenAI(**client_kwargs)
            initial_input = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": problem},
            ]
            total_budget = None
            if max_tokens is not None:
                total_budget = int(max_tokens)
            elif self._max_final_tokens is not None:
                total_budget = int(self._max_final_tokens) + max(0, int(self._reasoning_budget_tokens or 0))
            elif env("XAI_MAX_OUTPUT_TOKENS") is not None:
                total_budget = int(env("XAI_MAX_OUTPUT_TOKENS", "4096") or "4096")
            per_request_limit = XAI_DEFAULT_MAX_OUTPUT_TOKENS_PER_REQUEST
            if env("XAI_MAX_OUTPUT_TOKENS_PER_REQUEST") is not None:
                per_request_limit = max(
                    1,
                    int(env("XAI_MAX_OUTPUT_TOKENS_PER_REQUEST", str(per_request_limit)) or per_request_limit),
                )
            remaining_budget = total_budget or per_request_limit
            effort = (env("XAI_REASONING_EFFORT", XAI_DEFAULT_REASONING_EFFORT) or XAI_DEFAULT_REASONING_EFFORT).lower()
            reasoning = None
            if self.model_id in XAI_REASONING_MODELS:
                if effort not in XAI_REASONING_EFFORTS:
                    effort = XAI_DEFAULT_REASONING_EFFORT
                reasoning = {"effort": effort}

            request_payload = {
                "endpoint": sanitized_base_url(f"{base_url.rstrip('/')}/responses"),
                "model": self.model_id,
                "input": initial_input,
                "stream": False,
                "store": True,
                "timeout_seconds": timeout_seconds,
                "max_retries": max_retries,
                "max_output_tokens_total": total_budget,
                "max_output_tokens_per_request": per_request_limit,
            }
            if reasoning is not None:
                request_payload["reasoning"] = reasoning
            ensure_text_only_request(request_payload)

            responses: list[dict[str, Any]] = []
            request_steps: list[dict[str, Any]] = []
            prompt_tokens = 0
            completion_tokens = 0
            reasoning_tokens = 0
            cached_input_tokens = 0
            previous_response_id = None
            answer = ""
            provider_ticks_total = 0
            provider_ticks_seen = False

            while remaining_budget > 0:
                step_max_tokens = min(remaining_budget, per_request_limit)
                step_input: Any = initial_input if previous_response_id is None else XAI_CONTINUATION_INPUT
                step_kwargs: dict[str, Any] = {
                    "model": self.model_id,
                    "input": step_input,
                    "max_output_tokens": step_max_tokens,
                    "store": True,
                }
                if previous_response_id is not None:
                    step_kwargs["previous_response_id"] = previous_response_id
                if reasoning is not None:
                    step_kwargs["reasoning"] = reasoning
                step_request = {
                    "endpoint": request_payload["endpoint"],
                    "model": self.model_id,
                    "input": step_input,
                    "previous_response_id": previous_response_id,
                    "max_output_tokens": step_max_tokens,
                    "store": True,
                    "stream": False,
                    "timeout_seconds": timeout_seconds,
                }
                if reasoning is not None:
                    step_request["reasoning"] = reasoning
                ensure_text_only_request(step_request)
                request_steps.append(step_request)

                response, step_latency_ms = timed(lambda: client.responses.create(**step_kwargs))
                latency_ms += step_latency_ms
                raw_step = safe_dict(response)
                last_raw_response = raw_step
                usage = getattr(response, "usage", None) or raw_step.get("usage") or {}
                step_prompt = usage_value(usage, "input_tokens", "prompt_tokens")
                step_completion = usage_value(usage, "output_tokens", "completion_tokens")
                step_reasoning = usage_detail_value(usage, "output_tokens_details", "reasoning_tokens") or usage_detail_value(usage, "completion_tokens_details", "reasoning_tokens") or usage_value(usage, "reasoning_tokens")
                step_cached = usage_detail_value(usage, "input_tokens_details", "cached_tokens", "cached_input_tokens") or usage_detail_value(usage, "prompt_tokens_details", "cached_tokens", "cached_input_tokens") or usage_value(usage, "cached_input_tokens")
                prompt_tokens += step_prompt
                completion_tokens += step_completion
                reasoning_tokens += step_reasoning
                cached_input_tokens += step_cached
                text = response_text(response)
                response_id = getattr(response, "id", None) or raw_step.get("id")
                ticks = provider_cost_ticks(raw_step)
                if ticks is not None:
                    provider_ticks_seen = True
                    provider_ticks_total += ticks
                responses.append({
                    "request": step_request,
                    "response": raw_step,
                    "latency_ms": step_latency_ms,
                    "answer_chars": len(text.strip()),
                })
                remaining_budget -= step_max_tokens
                previous_response_id = str(response_id) if response_id else None
                if text.strip():
                    answer = text
                    break
                if not previous_response_id:
                    break

            cost = estimate_cost(
                "xai",
                self.model_id,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                cached_input_tokens=cached_input_tokens or None,
            )
            if provider_ticks_seen:
                provider_cost = provider_ticks_total / 10_000_000_000
                cost = {
                    **cost,
                    "total": round(provider_cost, 10),
                    "estimated": False,
                    "provider_reported": {"cost_in_usd_ticks": provider_ticks_total},
                    "pricing_source": "provider_response",
                }
            raw_response = {
                "endpoint": request_payload["endpoint"],
                "multi_request": {
                    "enabled": len(responses) > 1 or bool(total_budget and total_budget > per_request_limit),
                    "requests": len(responses),
                    "max_output_tokens_total": total_budget,
                    "max_output_tokens_per_request": per_request_limit,
                    "stopped_after_visible_output": bool(answer.strip()),
                },
                "responses": responses,
                "last_response": last_raw_response,
                "usage": {
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "output_tokens_details": {"reasoning_tokens": reasoning_tokens or None},
                    "input_tokens_details": {"cached_tokens": cached_input_tokens or None},
                },
            }
            finish = response_finish_reason(last_raw_response)
            error = None
            if not answer.strip():
                error = (
                    "xAI Responses API returned no visible output after "
                    f"{len(responses)} request(s) and {completion_tokens} output tokens"
                )

            return SolveResult(
                model=self.model_id,
                answer=answer,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost.get("total") or 0.0,
                latency_ms=latency_ms,
                raw_response=raw_response,
                error=error,
                provider="xai",
                requested_model_id=self.model_id,
                resolved_model_id=last_raw_response.get("model") or self.model_id,
                request={**request_payload, "steps": request_steps},
                usage={
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "reasoning_tokens": reasoning_tokens or None,
                    "cached_input_tokens": cached_input_tokens or None,
                    "cache_creation_input_tokens": None,
                    "raw": raw_response["usage"],
                    "source": "provider_response",
                },
                cost={**cost, "reasoning": None},
                finish_reason=finish,
                response_id=last_raw_response.get("id"),
                provider_timestamp=last_raw_response.get("created_at") or last_raw_response.get("created"),
            )
        except Exception as exc:
            result = error_result(self.model_id, exc, latency_ms=latency_ms)
            result.provider = "xai"
            result.requested_model_id = self.model_id
            result.resolved_model_id = last_raw_response.get("model") or self.model_id
            result.request = request_payload or None
            result.raw_response = last_raw_response
            return result
