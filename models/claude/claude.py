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
from ..pricing import ANTHROPIC_USD_PER_1M as PRICES_USD_PER_1M, estimate_cost, price_for
from ..telemetry import sanitized_base_url
from .versions import DEFAULT as DEFAULT_VERSION


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
                "stream": False,
            }
            ensure_text_only_request(request_payload)

            response, latency_ms = timed(
                lambda: client.messages.create(**kwargs)
            )

            prompt_tokens = int(getattr(response.usage, "input_tokens", 0) or 0)
            completion_tokens = int(getattr(response.usage, "output_tokens", 0) or 0)
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
            )
            answer = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            raw_response = safe_dict(response)

            return SolveResult(
                model=self.model_id,
                answer=answer,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=round(cost_usd, 8),
                latency_ms=latency_ms,
                raw_response=raw_response,
                provider="anthropic",
                requested_model_id=self.model_id,
                resolved_model_id=raw_response.get("model") or self.model_id,
                request=request_payload,
                cost={**cost, "cached_input": None, "reasoning": None},
            )
        except Exception as exc:
            return error_result(self.model_id, exc)
