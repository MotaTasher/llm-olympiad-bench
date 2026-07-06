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


GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_DEFAULT_TEMPERATURE = 0.2
GEMINI_DEFAULT_THINKING_LEVEL = "high"


def optional_positive_int(name: str) -> int | None:
    value = env(name)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def optional_positive_float(name: str) -> float | None:
    value = env(name)
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


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


def response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    parts: list[str] = []
    candidates = getattr(response, "candidates", None)
    if candidates is None and isinstance(response, dict):
        candidates = response.get("candidates")
    for candidate in candidates or []:
        content = candidate.get("content") if isinstance(candidate, dict) else getattr(candidate, "content", None)
        candidate_parts = content.get("parts") if isinstance(content, dict) else getattr(content, "parts", None)
        for part in candidate_parts or []:
            is_thought = part.get("thought") if isinstance(part, dict) else getattr(part, "thought", False)
            if is_thought:
                continue
            value = part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
            if isinstance(value, str):
                parts.append(value)
    return "\n".join(parts)


def finish_reason(raw_response: dict[str, Any]) -> str | None:
    candidates = raw_response.get("candidates")
    if isinstance(candidates, list) and candidates:
        first = candidates[0]
        if isinstance(first, dict) and first.get("finish_reason"):
            return str(first["finish_reason"])
        if isinstance(first, dict) and first.get("finishReason"):
            return str(first["finishReason"])
    return raw_response.get("finish_reason") or raw_response.get("finishReason")


class GeminiModel(BaseModel):
    def __init__(
        self,
        model: str | None = None,
        *,
        reasoning_budget_tokens: int | None = None,
        max_final_tokens: int | None = None,
    ) -> None:
        self._model = model or env("GEMINI_MODEL", DEFAULT_VERSION)
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
            api_key = require_env("GEMINI_API_KEY")
            from google import genai
            from google.genai import types

            timeout_seconds = optional_positive_float("GEMINI_TIMEOUT_SECONDS")
            client_kwargs: dict[str, Any] = {"api_key": api_key}
            if timeout_seconds is not None:
                client_kwargs["http_options"] = types.HttpOptions(timeout=int(timeout_seconds * 1000))
            client = genai.Client(**client_kwargs)

            max_output_tokens = (
                int(max_tokens)
                if max_tokens is not None
                else int(self._max_final_tokens)
                if self._max_final_tokens is not None
                else optional_positive_int("GEMINI_MAX_OUTPUT_TOKENS")
            )
            temperature = float(env("GEMINI_TEMPERATURE", str(GEMINI_DEFAULT_TEMPERATURE)) or GEMINI_DEFAULT_TEMPERATURE)
            thinking_level = (env("GEMINI_THINKING_LEVEL", GEMINI_DEFAULT_THINKING_LEVEL) or GEMINI_DEFAULT_THINKING_LEVEL).upper()
            thinking_enum = getattr(getattr(types, "ThinkingLevel", object), thinking_level, thinking_level)
            thinking_config = types.ThinkingConfig(thinking_level=thinking_enum)
            config_kwargs: dict[str, Any] = {
                "system_instruction": SYSTEM_PROMPT,
                "temperature": temperature,
                "thinking_config": thinking_config,
            }
            if max_output_tokens is not None:
                config_kwargs["max_output_tokens"] = int(max_output_tokens)
            config = types.GenerateContentConfig(**config_kwargs)

            request_payload = {
                "endpoint": sanitized_base_url(f"{GEMINI_ENDPOINT}/{self.model_id}:generateContent"),
                "model": self.model_id,
                "system_instruction": SYSTEM_PROMPT,
                "contents": problem,
                "max_output_tokens": max_output_tokens,
                "temperature": temperature,
                "thinking_config": {"thinking_level": thinking_level},
                "store": False,
            }
            ensure_text_only_request(request_payload)

            response, latency_ms = timed(
                lambda: client.models.generate_content(
                    model=self.model_id,
                    contents=problem,
                    config=config,
                )
            )
            raw_response = safe_dict(response)
            usage = getattr(response, "usage_metadata", None) or raw_response.get("usage_metadata") or raw_response.get("usageMetadata")
            prompt_tokens = usage_value(usage, "prompt_token_count", "promptTokenCount", "input_tokens", "inputTokens")
            completion_tokens = usage_value(usage, "candidates_token_count", "candidatesTokenCount", "output_tokens", "outputTokens")
            total_tokens = usage_value(usage, "total_token_count", "totalTokenCount", "total_tokens", "totalTokens")
            reasoning_tokens = usage_value(usage, "thoughts_token_count", "thoughtsTokenCount", "reasoning_tokens", "reasoningTokens") or None
            cached_input_tokens = usage_detail_value(usage, "cache_tokens_details", "cached_tokens", "cachedTokens") or usage_value(usage, "cached_content_token_count", "cachedContentTokenCount") or None
            answer = response_text(response)
            cost = estimate_cost(
                "google",
                self.model_id,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                cached_input_tokens=cached_input_tokens,
            )
            resolved_model = raw_response.get("model_version") or raw_response.get("modelVersion") or raw_response.get("model") or self.model_id

            return SolveResult(
                model=self.model_id,
                answer=answer,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost.get("total") or 0.0,
                latency_ms=latency_ms,
                raw_response=raw_response,
                provider="google",
                requested_model_id=self.model_id,
                resolved_model_id=resolved_model,
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
                finish_reason=finish_reason(raw_response),
                response_id=raw_response.get("id") or raw_response.get("response_id"),
                provider_timestamp=raw_response.get("create_time") or raw_response.get("createTime"),
            )
        except Exception as exc:
            result = error_result(self.model_id, exc, latency_ms=latency_ms)
            result.provider = "google"
            result.requested_model_id = self.model_id
            result.resolved_model_id = raw_response.get("model") or self.model_id
            result.request = request_payload or None
            result.raw_response = raw_response
            return result
