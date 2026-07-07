from __future__ import annotations

from typing import Any

from ..base import BaseModel, SolveResult
from ..common import (
    SYSTEM_PROMPT,
    empty_answer_error,
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


GEMINI_INTERACTIONS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_DEFAULT_TEMPERATURE = 0.2
GEMINI_DEFAULT_THINKING_LEVEL = "high"
GEMINI_DEFAULT_MAX_OUTPUT_TOKENS_PER_REQUEST = 65_536


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
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    if isinstance(response, dict):
        for key in ("output_text", "outputText", "text"):
            value = response.get(key)
            if isinstance(value, str):
                return value
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


def interaction_usage(response: Any, raw_response: dict[str, Any]) -> Any:
    for name in ("usage_metadata", "usageMetadata", "usage"):
        value = getattr(response, name, None)
        if value:
            return value
        value = raw_response.get(name)
        if value:
            return value
    return {}


def finish_reason(raw_response: dict[str, Any]) -> str | None:
    candidates = raw_response.get("candidates")
    if isinstance(candidates, list) and candidates:
        first = candidates[0]
        if isinstance(first, dict) and first.get("finish_reason"):
            return str(first["finish_reason"])
        if isinstance(first, dict) and first.get("finishReason"):
            return str(first["finishReason"])
    direct = raw_response.get("finish_reason") or raw_response.get("finishReason")
    if direct:
        return str(direct)
    for step in reversed(raw_response.get("steps") or []):
        if not isinstance(step, dict):
            continue
        for key in ("finish_reason", "finishReason", "status"):
            value = step.get(key)
            if value:
                return str(value)
        for nested_key in ("model_output", "modelOutput", "output"):
            nested = step.get(nested_key)
            if isinstance(nested, dict):
                for key in ("finish_reason", "finishReason", "status"):
                    value = nested.get(key)
                    if value:
                        return str(value)
    status = raw_response.get("status")
    return str(status) if status else None


def is_length_limited(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.upper()
    return normalized in {"MAX_TOKENS", "MAX_OUTPUT_TOKENS", "LENGTH"} or "MAX" in normalized or "LENGTH" in normalized


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

            total_budget = (
                int(max_tokens)
                if max_tokens is not None
                else int(self._max_final_tokens)
                if self._max_final_tokens is not None
                else optional_positive_int("GEMINI_MAX_OUTPUT_TOKENS")
            )
            per_request_limit = min(
                int(total_budget or GEMINI_DEFAULT_MAX_OUTPUT_TOKENS_PER_REQUEST),
                GEMINI_DEFAULT_MAX_OUTPUT_TOKENS_PER_REQUEST,
            )
            temperature = float(env("GEMINI_TEMPERATURE", str(GEMINI_DEFAULT_TEMPERATURE)) or GEMINI_DEFAULT_TEMPERATURE)
            thinking_level = (env("GEMINI_THINKING_LEVEL", GEMINI_DEFAULT_THINKING_LEVEL) or GEMINI_DEFAULT_THINKING_LEVEL).lower()
            generation_config: dict[str, Any] = {
                "thinking_level": thinking_level,
                "temperature": temperature,
            }
            if per_request_limit is not None:
                generation_config["max_output_tokens"] = int(per_request_limit)
            request_payload = {
                "endpoint": sanitized_base_url(GEMINI_INTERACTIONS_ENDPOINT),
                "model": self.model_id,
                "system_instruction": SYSTEM_PROMPT,
                "input": problem,
                "max_output_tokens_total": total_budget,
                "max_output_tokens_per_request": per_request_limit,
                "temperature": temperature,
                "thinking_config": {"thinking_level": thinking_level.upper()},
                "store": True,
            }
            ensure_text_only_request(request_payload)

            remaining_budget = int(total_budget or per_request_limit)
            previous_interaction_id: str | None = None
            responses: list[dict[str, Any]] = []
            request_steps: list[dict[str, Any]] = []
            answer_parts: list[str] = []
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            reasoning_tokens = 0
            cached_input_tokens = 0
            last_finish_reason: str | None = None
            resolved_model = self.model_id

            while remaining_budget > 0:
                step_max_tokens = min(per_request_limit, remaining_budget)
                step_input = (
                    problem
                    if previous_interaction_id is None
                    else "Continue from the previous reasoning and provide the final visible solution. Do not restart."
                )
                step_generation_config = {
                    **generation_config,
                    "max_output_tokens": int(step_max_tokens),
                }
                step_request = {
                    "model": self.model_id,
                    "input": step_input,
                    "system_instruction": SYSTEM_PROMPT,
                    "generation_config": step_generation_config,
                    "previous_interaction_id": previous_interaction_id,
                    "store": True,
                }
                request_steps.append(step_request)
                interaction_kwargs: dict[str, Any] = {
                    "model": self.model_id,
                    "input": step_input,
                    "system_instruction": SYSTEM_PROMPT,
                    "generation_config": step_generation_config,
                    "store": True,
                }
                if previous_interaction_id:
                    interaction_kwargs["previous_interaction_id"] = previous_interaction_id
                response, step_latency_ms = timed(
                    lambda: client.interactions.create(**interaction_kwargs)
                )
                latency_ms += step_latency_ms
                step_raw_response = safe_dict(response)
                raw_response = step_raw_response
                usage = interaction_usage(response, step_raw_response)
                step_prompt_tokens = usage_value(
                    usage,
                    "total_input_tokens",
                    "totalInputTokens",
                    "prompt_token_count",
                    "promptTokenCount",
                    "input_tokens",
                    "inputTokens",
                )
                step_completion_tokens = usage_value(
                    usage,
                    "total_output_tokens",
                    "totalOutputTokens",
                    "candidates_token_count",
                    "candidatesTokenCount",
                    "output_tokens",
                    "outputTokens",
                )
                step_total_tokens = usage_value(usage, "total_token_count", "totalTokenCount", "total_tokens", "totalTokens")
                step_reasoning_tokens = usage_value(
                    usage,
                    "total_thought_tokens",
                    "totalThoughtTokens",
                    "thoughts_token_count",
                    "thoughtsTokenCount",
                    "reasoning_tokens",
                    "reasoningTokens",
                ) or 0
                step_cached_tokens = usage_detail_value(
                    usage,
                    "cache_tokens_details",
                    "cached_tokens",
                    "cachedTokens",
                ) or usage_value(
                    usage,
                    "total_cached_tokens",
                    "totalCachedTokens",
                    "cached_content_token_count",
                    "cachedContentTokenCount",
                ) or 0
                prompt_tokens += step_prompt_tokens
                completion_tokens += step_completion_tokens
                total_tokens += step_total_tokens
                reasoning_tokens += step_reasoning_tokens
                cached_input_tokens += step_cached_tokens
                text = response_text(response)
                if text.strip():
                    answer_parts.append(text)
                step_finish_reason = finish_reason(step_raw_response)
                last_finish_reason = step_finish_reason or last_finish_reason
                interaction_id = getattr(response, "id", None) or step_raw_response.get("id")
                resolved_model = (
                    step_raw_response.get("model_version")
                    or step_raw_response.get("modelVersion")
                    or step_raw_response.get("model")
                    or resolved_model
                )
                responses.append(
                    {
                        "request": step_request,
                        "response": step_raw_response,
                        "latency_ms": step_latency_ms,
                        "answer_chars": len(text.strip()),
                    }
                )
                previous_interaction_id = str(interaction_id) if interaction_id else None
                remaining_budget -= step_max_tokens
                if not is_length_limited(step_finish_reason) and text.strip():
                    break
                if not previous_interaction_id:
                    break

            answer = "\n\n".join(part.strip() for part in answer_parts if part.strip())
            billable_output_tokens = completion_tokens + reasoning_tokens
            cost = estimate_cost(
                "google",
                self.model_id,
                input_tokens=prompt_tokens,
                output_tokens=billable_output_tokens,
                cached_input_tokens=cached_input_tokens or None,
            )
            raw_response = {
                "endpoint": sanitized_base_url(GEMINI_INTERACTIONS_ENDPOINT),
                "multi_request": {
                    "enabled": len(responses) > 1 or bool(total_budget and total_budget > per_request_limit),
                    "requests": len(responses),
                    "max_output_tokens_total": total_budget,
                    "max_output_tokens_per_request": per_request_limit,
                    "stopped_after_non_limited_visible_output": bool(answer.strip() and not is_length_limited(last_finish_reason)),
                },
                "responses": responses,
                "last_response": raw_response,
                "usage": {
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": total_tokens or prompt_tokens + billable_output_tokens,
                    "total_input_tokens": prompt_tokens,
                    "total_output_tokens": completion_tokens,
                    "total_thought_tokens": reasoning_tokens or None,
                    "total_cached_tokens": cached_input_tokens or None,
                    "output_tokens_details": {"reasoning_tokens": reasoning_tokens or None},
                    "input_tokens_details": {"cached_tokens": cached_input_tokens or None},
                    "billable_output_tokens": billable_output_tokens,
                },
            }
            error = None
            if not answer.strip():
                error = empty_answer_error(
                    "Gemini Interactions API",
                    generated_tokens=billable_output_tokens,
                    finish_reason=last_finish_reason,
                    request_count=len(responses),
                )

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
                request={**request_payload, "steps": request_steps},
                usage={
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": total_tokens or prompt_tokens + billable_output_tokens,
                    "reasoning_tokens": reasoning_tokens or None,
                    "cached_input_tokens": cached_input_tokens or None,
                    "cache_creation_input_tokens": None,
                    "raw": raw_response["usage"],
                    "source": "provider_response" if responses else "legacy_fields",
                },
                cost={**cost, "reasoning": None},
                finish_reason=last_finish_reason,
                response_id=(raw_response.get("last_response") or {}).get("id"),
                provider_timestamp=(raw_response.get("last_response") or {}).get("create_time") or (raw_response.get("last_response") or {}).get("createTime"),
                error=error,
            )
        except Exception as exc:
            result = error_result(self.model_id, exc, latency_ms=latency_ms)
            result.provider = "google"
            result.requested_model_id = self.model_id
            result.resolved_model_id = raw_response.get("model") or self.model_id
            result.request = request_payload or None
            result.raw_response = raw_response
            return result
