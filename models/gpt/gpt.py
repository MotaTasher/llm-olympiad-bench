from __future__ import annotations

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
from ..pricing import OPENAI_USD_PER_1M as PRICES_USD_PER_1M, estimate_cost, price_for
from ..telemetry import sanitized_base_url
from .versions import DEFAULT as DEFAULT_VERSION


OPENAI_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"
OPENAI_CONTINUATION_INPUT = "Continue."
OPENAI_MAX_OUTPUT_TOKENS_BY_MODEL = {
    "gpt-5.5": 128_000,
    "gpt-5.4-mini": 128_000,
}
OPENAI_DEFAULT_MAX_OUTPUT_TOKENS = 128_000
OPENAI_DEFAULT_TIMEOUT_SECONDS = 7_200.0


def positive_float_env(name: str, default: float) -> float:
    value = env(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def optional_nonnegative_int_env(name: str) -> int | None:
    value = env(name)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def max_output_tokens_for_model(model_id: str) -> int:
    for prefix, limit in OPENAI_MAX_OUTPUT_TOKENS_BY_MODEL.items():
        if model_id == prefix or model_id.startswith(f"{prefix}-"):
            return limit
    return OPENAI_DEFAULT_MAX_OUTPUT_TOKENS


def usage_value(usage: object, *names: str) -> int:
    for name in names:
        if isinstance(usage, dict):
            value = usage.get(name)
        else:
            value = getattr(usage, name, None) if usage is not None else None
        if value not in {None, ""}:
            return int(value or 0)
    return 0


def usage_detail_value(usage: object, detail_name: str, value_name: str) -> int | None:
    if isinstance(usage, dict):
        detail = usage.get(detail_name)
    else:
        detail = getattr(usage, detail_name, None) if usage is not None else None
    if isinstance(detail, dict):
        value = detail.get(value_name)
    else:
        value = getattr(detail, value_name, None) if detail is not None else None
    return int(value) if value not in {None, ""} else None


def response_text(response: object) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str):
        return text
    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        contents = item.get("content", []) if isinstance(item, dict) else getattr(item, "content", [])
        for content in contents or []:
            value = content.get("text") if isinstance(content, dict) else getattr(content, "text", None)
            if isinstance(value, str):
                parts.append(value)
    return "\n".join(parts)


def finish_reason(raw_response: dict) -> str | None:
    incomplete_details = raw_response.get("incomplete_details")
    if isinstance(incomplete_details, dict) and incomplete_details.get("reason"):
        return str(incomplete_details.get("reason"))
    status = raw_response.get("status")
    return str(status) if status else None


class GPTModel(BaseModel):
    def __init__(
        self,
        model: str | None = None,
        *,
        reasoning_budget_tokens: int | None = None,
        max_final_tokens: int | None = None,
    ) -> None:
        self._model = model or env("OPENAI_MODEL", DEFAULT_VERSION)
        self._reasoning_budget_tokens = reasoning_budget_tokens
        self._max_final_tokens = max_final_tokens

    @property
    def model_id(self) -> str:
        return self._model

    def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult:
        request_payload = {}
        last_raw_response: dict = {}
        latency_ms = 0
        try:
            from openai import OpenAI

            timeout_seconds = positive_float_env("OPENAI_TIMEOUT_SECONDS", OPENAI_DEFAULT_TIMEOUT_SECONDS)
            max_retries = optional_nonnegative_int_env("OPENAI_MAX_RETRIES")
            client_kwargs = {
                "api_key": require_env("OPENAI_API_KEY"),
                "timeout": timeout_seconds,
            }
            if max_retries is not None:
                client_kwargs["max_retries"] = max_retries
            client = OpenAI(**client_kwargs)
            total_budget = None
            if max_tokens is not None:
                total_budget = int(max_tokens)
            elif self._max_final_tokens is not None:
                budget = max(0, int(self._reasoning_budget_tokens or 0))
                total_budget = int(self._max_final_tokens) + budget
            elif env("OPENAI_MAX_COMPLETION_TOKENS") is not None:
                total_budget = int(env("OPENAI_MAX_COMPLETION_TOKENS", "4096") or "4096")

            per_request_limit = max_output_tokens_for_model(self.model_id)
            remaining_budget = total_budget or per_request_limit
            reasoning = None
            if env("OPENAI_REASONING_EFFORT") is not None:
                reasoning = {"effort": env("OPENAI_REASONING_EFFORT")}
            request_payload = {
                "model": self.model_id,
                "instructions": SYSTEM_PROMPT,
                "input": problem,
                "endpoint": sanitized_base_url(OPENAI_RESPONSES_ENDPOINT),
                "stream": False,
                "store": True,
                "max_output_tokens_total": total_budget,
                "max_output_tokens_per_request": per_request_limit,
                "timeout_seconds": timeout_seconds,
                "max_retries": max_retries,
            }
            if reasoning is not None:
                request_payload["reasoning"] = reasoning
            ensure_text_only_request(request_payload)

            responses = []
            request_steps = []
            prompt_tokens = 0
            completion_tokens = 0
            reasoning_tokens = 0
            cached_input_tokens = 0
            previous_response_id = None
            answer = ""

            while remaining_budget > 0:
                step_max_tokens = min(remaining_budget, per_request_limit)
                step_input = problem if previous_response_id is None else OPENAI_CONTINUATION_INPUT
                step_kwargs = {
                    "model": self.model_id,
                    "input": step_input,
                    "max_output_tokens": step_max_tokens,
                    "store": True,
                }
                if previous_response_id is None:
                    step_kwargs["instructions"] = SYSTEM_PROMPT
                else:
                    step_kwargs["previous_response_id"] = previous_response_id
                if reasoning is not None:
                    step_kwargs["reasoning"] = reasoning

                step_request = {
                    "endpoint": sanitized_base_url(OPENAI_RESPONSES_ENDPOINT),
                    "model": self.model_id,
                    "input": step_input,
                    "instructions": SYSTEM_PROMPT if previous_response_id is None else None,
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
                raw_response = safe_dict(response)
                last_raw_response = raw_response
                usage = getattr(response, "usage", None)
                step_prompt_tokens = usage_value(usage, "input_tokens", "prompt_tokens")
                step_completion_tokens = usage_value(usage, "output_tokens", "completion_tokens")
                step_reasoning_tokens = (
                    usage_detail_value(usage, "output_tokens_details", "reasoning_tokens") or 0
                )
                step_cached_tokens = (
                    usage_detail_value(usage, "input_tokens_details", "cached_tokens") or 0
                )
                prompt_tokens += step_prompt_tokens
                completion_tokens += step_completion_tokens
                reasoning_tokens += step_reasoning_tokens
                cached_input_tokens += step_cached_tokens
                text = response_text(response)
                response_id = getattr(response, "id", None) or raw_response.get("id")
                responses.append(
                    {
                        "request": step_request,
                        "response": raw_response,
                        "latency_ms": step_latency_ms,
                        "answer_chars": len(text.strip()),
                    }
                )
                previous_response_id = str(response_id) if response_id else None
                remaining_budget -= step_max_tokens
                if text.strip():
                    answer = text
                    break
                if not previous_response_id:
                    break

            input_per_1m, output_per_1m = price_for(
                self.model_id, PRICES_USD_PER_1M, PRICES_USD_PER_1M["gpt-4o"]
            )
            cost_usd = (
                prompt_tokens * input_per_1m / 1_000_000
                + completion_tokens * output_per_1m / 1_000_000
            )
            cost = estimate_cost(
                "openai",
                self.model_id,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                reasoning_tokens=reasoning_tokens or None,
            )
            raw_response = {
                "endpoint": sanitized_base_url(OPENAI_RESPONSES_ENDPOINT),
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
            error = None
            if not answer.strip():
                error = (
                    "OpenAI Responses API returned no visible output after "
                    f"{len(responses)} request(s) and {completion_tokens} output tokens"
                )

            return SolveResult(
                model=self.model_id,
                answer=answer,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=round(cost_usd, 8),
                latency_ms=latency_ms,
                raw_response=raw_response,
                error=error,
                provider="openai",
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
                cost={**cost, "cached_input": None},
                finish_reason=finish_reason(last_raw_response),
                response_id=last_raw_response.get("id"),
                provider_timestamp=last_raw_response.get("created_at") or last_raw_response.get("created"),
            )
        except Exception as exc:
            result = error_result(self.model_id, exc, latency_ms=latency_ms)
            result.provider = "openai"
            result.requested_model_id = self.model_id
            result.resolved_model_id = last_raw_response.get("model") or self.model_id
            result.request = request_payload or None
            result.raw_response = last_raw_response or {}
            return result
