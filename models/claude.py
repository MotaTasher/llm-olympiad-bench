from __future__ import annotations

from .base import BaseModel, SolveResult
from .common import SYSTEM_PROMPT, env, error_result, price_for, require_env, safe_dict, timed


# USD per 1M tokens: input, output.
PRICES_USD_PER_1M = {
    "claude-opus-4-5": (15.00, 75.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (0.80, 4.00),
}


class ClaudeModel(BaseModel):
    def __init__(self, model: str | None = None) -> None:
        self._model = model or env("ANTHROPIC_MODEL", "claude-opus-4-5")

    @property
    def model_id(self) -> str:
        return self._model

    def solve(self, problem: str) -> SolveResult:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=require_env("ANTHROPIC_API_KEY"))

            response, latency_ms = timed(
                lambda: client.messages.create(
                    model=self.model_id,
                    max_tokens=int(env("ANTHROPIC_MAX_TOKENS", "4096") or "4096"),
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": problem}],
                )
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
            answer = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )

            return SolveResult(
                model=self.model_id,
                answer=answer,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=round(cost_usd, 8),
                latency_ms=latency_ms,
                raw_response=safe_dict(response),
            )
        except Exception as exc:
            return error_result(self.model_id, exc)
