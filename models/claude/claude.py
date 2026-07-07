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
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=require_env("ANTHROPIC_API_KEY"))
            if max_tokens is not None:
                max_tokens = int(max_tokens)
            elif self._max_final_tokens is not None:
                max_tokens = int(self._max_final_tokens)
            else:
                max_tokens = int(env("ANTHROPIC_MAX_TOKENS", "4096") or "4096")
            kwargs = {
                "model": self.model_id,
                "max_tokens": max_tokens,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": problem}],
            }
            if self._reasoning_budget_tokens is not None:
                budget_tokens = int(self._reasoning_budget_tokens)
                thinking_budget = str(budget_tokens)
            else:
                thinking_budget = env("ANTHROPIC_THINKING_BUDGET_TOKENS")
                budget_tokens = int(thinking_budget or "0") if thinking_budget is not None else 0
            if thinking_budget is not None:
                if budget_tokens > 0:
                    if self._max_final_tokens is not None:
                        kwargs["max_tokens"] = max_tokens + budget_tokens
                    elif max_tokens <= budget_tokens:
                        raise RuntimeError(
                            "ANTHROPIC_MAX_TOKENS must be greater than "
                            "ANTHROPIC_THINKING_BUDGET_TOKENS when extended thinking is enabled"
                        )
                    kwargs["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": budget_tokens,
                    }
            request_payload = {
                **kwargs,
                "endpoint": sanitized_base_url("https://api.anthropic.com/v1/messages"),
            }
            use_streaming = max_tokens > ANTHROPIC_NONSTREAMING_MAX_TOKENS
            request_payload["stream"] = use_streaming
            ensure_text_only_request(request_payload)

            if use_streaming:
                response, latency_ms = timed(
                    lambda: self._create_streaming_message(client, kwargs)
                )
            else:
                response, latency_ms = timed(lambda: client.messages.create(**kwargs))

            provider_usage = getattr(response, "usage", None)
            prompt_tokens = int(usage_value(provider_usage, "input_tokens") or 0)
            completion_tokens = int(usage_value(provider_usage, "output_tokens") or 0)
            reasoning_tokens = (
                usage_detail_value(provider_usage, "output_tokens_details", "reasoning_tokens", "reasoningTokens")
                or usage_value(provider_usage, "reasoning_tokens", "reasoningTokens")
            )
            cached_input_tokens = usage_value(provider_usage, "cache_read_input_tokens")
            cache_creation_input_tokens = usage_value(provider_usage, "cache_creation_input_tokens")
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
            answer = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            raw_response = safe_dict(response)
            finish = raw_response.get("stop_reason") or raw_response.get("stopReason")
            error = None
            if not answer.strip():
                error = empty_answer_error(
                    "Anthropic Messages API",
                    generated_tokens=completion_tokens,
                    finish_reason=str(finish) if finish else None,
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
                resolved_model_id=raw_response.get("model") or self.model_id,
                request=request_payload,
                usage={
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "cached_input_tokens": cached_input_tokens,
                    "cache_creation_input_tokens": cache_creation_input_tokens,
                    "raw": safe_dict(provider_usage),
                    "source": "provider_response" if provider_usage else "legacy_fields",
                },
                cost={**cost, "cached_input": None},
            )
        except Exception as exc:
            result = error_result(self.model_id, exc)
            result.provider = "anthropic"
            result.requested_model_id = self.model_id
            result.resolved_model_id = self.model_id
            return result

    @staticmethod
    def _create_streaming_message(client, kwargs):
        with client.messages.stream(**kwargs) as stream:
            return stream.get_final_message()
