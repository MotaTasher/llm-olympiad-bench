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
from ..pricing import ANTHROPIC_USD_PER_1M as PRICES_USD_PER_1M, estimate_cost, price_for
from ..telemetry import sanitized_base_url
from .versions import DEFAULT as DEFAULT_VERSION


ANTHROPIC_NONSTREAMING_MAX_TOKENS = 21333
ANTHROPIC_CONTINUATION_INPUT = "Continue."
ANTHROPIC_MAX_OUTPUT_TOKENS_BY_MODEL = {
    "claude-opus-4-8": 128_000,
    "claude-haiku-4-5-20251001": 64_000,
}
ANTHROPIC_DEFAULT_MAX_OUTPUT_TOKENS = 64_000


def usage_value(usage: Any, *names: str) -> int | None:
    for name in names:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        if value not in {None, ""}:
            return int(value or 0)
    return None


def usage_detail_value(usage: Any, detail_name: str, *names: str) -> int | None:
    detail = usage.get(detail_name) if isinstance(usage, dict) else getattr(usage, detail_name, None)
    for name in names:
        value = detail.get(name) if isinstance(detail, dict) else getattr(detail, name, None)
        if value not in {None, ""}:
            return int(value or 0)
    return None


def max_output_tokens_for_model(model_id: str) -> int:
    for prefix, limit in ANTHROPIC_MAX_OUTPUT_TOKENS_BY_MODEL.items():
        if model_id == prefix or model_id.startswith(f"{prefix}-"):
            return limit
    return ANTHROPIC_DEFAULT_MAX_OUTPUT_TOKENS


def content_blocks_for_request(content: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in content or []:
        data = safe_dict(block)
        if data:
            blocks.append(data)
    return blocks


class ClaudeModel(BaseModel):
    def __init__(
        self,
        model: str | None = None,
        *,
        reasoning_budget_tokens: int | None = None,
        max_final_tokens: int | None = None,
    ) -> None:
        self._model = model or env("ANTHROPIC_MODEL", DEFAULT_VERSION)
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
            import anthropic

            client = anthropic.Anthropic(api_key=require_env("ANTHROPIC_API_KEY"))
            if self._reasoning_budget_tokens is not None:
                budget_tokens = int(self._reasoning_budget_tokens)
                thinking_budget = str(budget_tokens)
            else:
                thinking_budget = env("ANTHROPIC_THINKING_BUDGET_TOKENS")
                budget_tokens = int(thinking_budget or "0") if thinking_budget is not None else 0

            if max_tokens is not None:
                total_budget = int(max_tokens)
            elif self._max_final_tokens is not None:
                total_budget = int(self._max_final_tokens) + max(0, budget_tokens)
            else:
                total_budget = int(env("ANTHROPIC_MAX_TOKENS", "4096") or "4096")

            per_request_limit = max_output_tokens_for_model(self.model_id)
            remaining_budget = total_budget
            messages: list[dict[str, Any]] = [{"role": "user", "content": problem}]
            request_payload = {
                "model": self.model_id,
                "system": SYSTEM_PROMPT,
                "endpoint": sanitized_base_url("https://api.anthropic.com/v1/messages"),
                "max_output_tokens_total": total_budget,
                "max_output_tokens_per_request": per_request_limit,
                "stream": total_budget > ANTHROPIC_NONSTREAMING_MAX_TOKENS,
            }
            if thinking_budget is not None:
                if budget_tokens > 0:
                    if per_request_limit <= budget_tokens:
                        raise RuntimeError(
                            "Claude per-request max_tokens must be greater than "
                            "ANTHROPIC_THINKING_BUDGET_TOKENS when extended thinking is enabled"
                        )
                    request_payload["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": budget_tokens,
                    }
            ensure_text_only_request(request_payload)

            responses = []
            request_steps = []
            prompt_tokens = 0
            completion_tokens = 0
            reasoning_tokens = 0
            cached_input_tokens = 0
            cache_creation_input_tokens = 0
            answer = ""
            finish = None

            while remaining_budget > 0:
                step_max_tokens = min(remaining_budget, per_request_limit)
                if budget_tokens > 0 and step_max_tokens <= budget_tokens:
                    raise RuntimeError(
                        "Claude step max_tokens must be greater than "
                        "ANTHROPIC_THINKING_BUDGET_TOKENS when extended thinking is enabled"
                    )
                kwargs: dict[str, Any] = {
                    "model": self.model_id,
                    "max_tokens": step_max_tokens,
                    "system": SYSTEM_PROMPT,
                    "messages": messages,
                }
                if budget_tokens > 0:
                    kwargs["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": budget_tokens,
                    }
                use_streaming = step_max_tokens > ANTHROPIC_NONSTREAMING_MAX_TOKENS
                step_request = {
                    "model": self.model_id,
                    "max_tokens": step_max_tokens,
                    "system": SYSTEM_PROMPT,
                    "messages": messages,
                    "endpoint": sanitized_base_url("https://api.anthropic.com/v1/messages"),
                    "stream": use_streaming,
                }
                if budget_tokens > 0:
                    step_request["thinking"] = kwargs["thinking"]
                ensure_text_only_request(step_request)
                request_steps.append(step_request)

                if use_streaming:
                    response, step_latency_ms = timed(
                        lambda: self._create_streaming_message(client, kwargs)
                    )
                else:
                    response, step_latency_ms = timed(lambda: client.messages.create(**kwargs))
                latency_ms += step_latency_ms

                raw_response = safe_dict(response)
                last_raw_response = raw_response
                provider_usage = getattr(response, "usage", None)
                step_prompt_tokens = int(usage_value(provider_usage, "input_tokens") or 0)
                step_completion_tokens = int(usage_value(provider_usage, "output_tokens") or 0)
                step_reasoning_tokens = (
                    usage_detail_value(provider_usage, "output_tokens_details", "reasoning_tokens", "reasoningTokens")
                    or usage_value(provider_usage, "reasoning_tokens", "reasoningTokens")
                    or 0
                )
                step_cached_input_tokens = usage_value(provider_usage, "cache_read_input_tokens") or 0
                step_cache_creation_input_tokens = usage_value(provider_usage, "cache_creation_input_tokens") or 0
                prompt_tokens += step_prompt_tokens
                completion_tokens += step_completion_tokens
                reasoning_tokens += step_reasoning_tokens
                cached_input_tokens += step_cached_input_tokens
                cache_creation_input_tokens += step_cache_creation_input_tokens
                text = "".join(
                    block.text for block in response.content if getattr(block, "type", None) == "text"
                )
                finish = raw_response.get("stop_reason") or raw_response.get("stopReason")
                responses.append(
                    {
                        "request": step_request,
                        "response": raw_response,
                        "latency_ms": step_latency_ms,
                        "answer_chars": len(text.strip()),
                    }
                )
                remaining_budget -= step_max_tokens
                if text.strip():
                    answer = text
                    break
                assistant_content = content_blocks_for_request(getattr(response, "content", None))
                if not assistant_content:
                    break
                messages = [
                    *messages,
                    {"role": "assistant", "content": assistant_content},
                    {"role": "user", "content": ANTHROPIC_CONTINUATION_INPUT},
                ]

            input_per_1m, output_per_1m = price_for(
                self.model_id, PRICES_USD_PER_1M, PRICES_USD_PER_1M["claude-opus-4-5"]
            )
            cost_usd = (
                prompt_tokens * input_per_1m / 1_000_000
                + completion_tokens * output_per_1m / 1_000_000
            )
            cost = estimate_cost(
                "anthropic",
                self.model_id,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                reasoning_tokens=reasoning_tokens,
            )
            raw_response = {
                "endpoint": sanitized_base_url("https://api.anthropic.com/v1/messages"),
                "multi_request": {
                    "enabled": len(responses) > 1 or total_budget > per_request_limit,
                    "requests": len(responses),
                    "max_output_tokens_total": total_budget,
                    "max_output_tokens_per_request": per_request_limit,
                    "stopped_after_visible_output": bool(answer.strip()),
                    "continuation": "assistant_content_blocks",
                },
                "responses": responses,
                "last_response": last_raw_response,
                "usage": {
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "output_tokens_details": {"reasoning_tokens": reasoning_tokens or None},
                    "cache_read_input_tokens": cached_input_tokens or None,
                    "cache_creation_input_tokens": cache_creation_input_tokens or None,
                },
            }
            error = None
            if not answer.strip():
                error = empty_answer_error(
                    "Anthropic Messages API",
                    generated_tokens=completion_tokens,
                    finish_reason=str(finish) if finish else None,
                    request_count=len(responses),
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
                provider="anthropic",
                requested_model_id=self.model_id,
                resolved_model_id=last_raw_response.get("model") or self.model_id,
                request={**request_payload, "steps": request_steps},
                usage={
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "reasoning_tokens": reasoning_tokens or None,
                    "cached_input_tokens": cached_input_tokens or None,
                    "cache_creation_input_tokens": cache_creation_input_tokens or None,
                    "raw": raw_response["usage"],
                    "source": "provider_response" if responses else "legacy_fields",
                },
                cost={**cost, "cached_input": None},
                finish_reason=str(finish) if finish else None,
                response_id=last_raw_response.get("id"),
                provider_timestamp=last_raw_response.get("created_at") or last_raw_response.get("created"),
            )
        except Exception as exc:
            result = error_result(self.model_id, exc, latency_ms=latency_ms)
            result.provider = "anthropic"
            result.requested_model_id = self.model_id
            result.resolved_model_id = last_raw_response.get("model") or self.model_id
            result.request = request_payload or None
            result.raw_response = last_raw_response or {}
            return result

    @staticmethod
    def _create_streaming_message(client, kwargs):
        with client.messages.stream(**kwargs) as stream:
            return stream.get_final_message()
