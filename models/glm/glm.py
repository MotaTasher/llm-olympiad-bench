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
ZAI_DEFAULT_TIMEOUT_SECONDS = 7200.0
ZAI_DEFAULT_MAX_OUTPUT_TOKENS_PER_REQUEST = 128_000
ZAI_CONTINUATION_INPUT = "Continue the reasoning and provide the complete final answer."
ZAI_REASONING_EFFORT_MODELS = {"glm-5.2"}
ZAI_STREAMING_MODELS = {"glm-5.2"}


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


def object_value(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def collect_streaming_response(stream: Any) -> dict[str, Any]:
    """Collect an OpenAI-compatible Z.AI stream into one chat-completion shape."""
    response: dict[str, Any] = {}
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
    try:
        for chunk in stream:
            raw_chunk = safe_dict(chunk)
            for name in ("id", "model", "created", "system_fingerprint"):
                value = object_value(chunk, name)
                if value is not None:
                    response[name] = value
            chunk_usage = object_value(chunk, "usage")
            if chunk_usage is not None:
                usage = safe_dict(chunk_usage)
            choice = first_choice(chunk)
            if choice is None:
                continue
            chunk_finish = object_value(choice, "finish_reason")
            if chunk_finish:
                finish_reason = str(chunk_finish)
            delta = object_value(choice, "delta") or {}
            content = object_value(delta, "content", "") or ""
            reasoning = object_value(delta, "reasoning_content", "") or ""
            if content:
                content_parts.append(str(content))
            if reasoning:
                reasoning_parts.append(str(reasoning))
            # Some compatible endpoints expose usage only in the raw chunk.
            if usage is None and isinstance(raw_chunk.get("usage"), dict):
                usage = raw_chunk["usage"]
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()

    message: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts)}
    if reasoning_parts:
        message["reasoning_content"] = "".join(reasoning_parts)
    response["choices"] = [{"index": 0, "finish_reason": finish_reason, "message": message}]
    if usage is not None:
        response["usage"] = usage
    return response


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
        last_raw_response: dict[str, Any] = {}
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
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": problem},
            ]
            total_budget = None
            if max_tokens is not None:
                total_budget = int(max_tokens)
            elif self._max_final_tokens is not None:
                total_budget = int(self._max_final_tokens) + max(0, int(self._reasoning_budget_tokens or 0))
            elif env("ZAI_MAX_TOKENS") is not None:
                total_budget = int(env("ZAI_MAX_TOKENS", "4096") or "4096")
            per_request_limit = ZAI_DEFAULT_MAX_OUTPUT_TOKENS_PER_REQUEST
            if env("ZAI_MAX_TOKENS_PER_REQUEST") is not None:
                per_request_limit = max(
                    1,
                    int(env("ZAI_MAX_TOKENS_PER_REQUEST", str(per_request_limit)) or per_request_limit),
                )
            remaining_budget = total_budget or per_request_limit
            use_streaming = self.model_id in ZAI_STREAMING_MODELS

            extra_body: dict[str, Any] = {}
            thinking = env("ZAI_THINKING", ZAI_DEFAULT_THINKING) or ZAI_DEFAULT_THINKING
            if thinking:
                extra_body["thinking"] = {"type": thinking}
            if self.model_id in ZAI_REASONING_EFFORT_MODELS:
                extra_body["reasoning_effort"] = env("ZAI_REASONING_EFFORT", ZAI_DEFAULT_REASONING_EFFORT) or ZAI_DEFAULT_REASONING_EFFORT
            extra_body["clear_thinking"] = False

            request_payload = {
                "endpoint": sanitized_base_url(f"{base_url.rstrip('/')}/chat/completions"),
                "model": self.model_id,
                "messages": messages,
                "stream": use_streaming,
                "timeout_seconds": timeout_seconds,
                "max_retries": max_retries,
                "max_output_tokens_total": total_budget,
                "max_output_tokens_per_request": per_request_limit,
                **extra_body,
            }
            ensure_text_only_request(request_payload)

            responses: list[dict[str, Any]] = []
            request_steps: list[dict[str, Any]] = []
            prompt_tokens = 0
            completion_tokens = 0
            reasoning_tokens = 0
            cached_input_tokens = 0
            answer = ""

            while remaining_budget > 0:
                step_max_tokens = min(remaining_budget, per_request_limit)
                kwargs: dict[str, Any] = {
                    "max_tokens": step_max_tokens,
                    "extra_body": dict(extra_body),
                    "stream": use_streaming,
                }
                if use_streaming:
                    kwargs["stream_options"] = {"include_usage": True}
                if env("ZAI_TEMPERATURE") is not None:
                    kwargs["temperature"] = float(env("ZAI_TEMPERATURE", "0.2") or "0.2")
                step_request = {
                    "endpoint": request_payload["endpoint"],
                    "model": self.model_id,
                    "messages": safe_dict(messages),
                    "max_tokens": step_max_tokens,
                    "stream": use_streaming,
                    "timeout_seconds": timeout_seconds,
                    **extra_body,
                }
                if "temperature" in kwargs:
                    step_request["temperature"] = kwargs["temperature"]
                ensure_text_only_request(step_request)
                request_steps.append(step_request)

                response, step_latency_ms = timed(
                    lambda: client.chat.completions.create(
                        model=self.model_id,
                        messages=messages,
                        **kwargs,
                    )
                )
                if use_streaming:
                    response, collect_latency_ms = timed(lambda: collect_streaming_response(response))
                    step_latency_ms += collect_latency_ms
                latency_ms += step_latency_ms
                raw_step = safe_dict(response)
                last_raw_response = raw_step
                usage = getattr(response, "usage", None) or raw_step.get("usage") or {}
                step_prompt = usage_value(usage, "prompt_tokens", "input_tokens")
                step_completion = usage_value(usage, "completion_tokens", "output_tokens")
                step_reasoning = usage_detail_value(usage, "completion_tokens_details", "reasoning_tokens") or usage_detail_value(usage, "output_tokens_details", "reasoning_tokens") or usage_value(usage, "reasoning_tokens")
                step_cached = usage_detail_value(usage, "prompt_tokens_details", "cached_tokens", "cached_input_tokens") or usage_detail_value(usage, "input_tokens_details", "cached_tokens", "cached_input_tokens") or usage_value(usage, "cached_input_tokens")
                prompt_tokens += step_prompt
                completion_tokens += step_completion
                reasoning_tokens += step_reasoning
                cached_input_tokens += step_cached
                message = first_choice_message(response)
                text = (message.get("content") if isinstance(message, dict) else getattr(message, "content", "")) or ""
                reasoning_content = message.get("reasoning_content") if isinstance(message, dict) else getattr(message, "reasoning_content", None)
                if reasoning_content:
                    raw_step["reasoning_content"] = reasoning_content
                responses.append({
                    "request": step_request,
                    "response": raw_step,
                    "latency_ms": step_latency_ms,
                    "answer_chars": len(text.strip()),
                })
                remaining_budget -= step_max_tokens
                if text.strip():
                    answer = text
                    break
                if remaining_budget <= 0 or not reasoning_content:
                    break
                messages.append({
                    "role": "assistant",
                    "content": text,
                    "reasoning_content": reasoning_content,
                })
                messages.append({"role": "user", "content": ZAI_CONTINUATION_INPUT})

            cost = estimate_cost(
                "zai",
                self.model_id,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                cached_input_tokens=cached_input_tokens or None,
            )
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
            finish = choice_finish_reason(last_raw_response)
            error = None
            if not answer.strip():
                error = (
                    "Z.AI Chat Completions API returned no visible output after "
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
                provider="zai",
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
                provider_timestamp=last_raw_response.get("created"),
            )
        except Exception as exc:
            result = error_result(self.model_id, exc, latency_ms=latency_ms)
            result.provider = "zai"
            result.requested_model_id = self.model_id
            result.resolved_model_id = last_raw_response.get("model") or self.model_id
            result.request = request_payload or None
            result.raw_response = last_raw_response
            return result
