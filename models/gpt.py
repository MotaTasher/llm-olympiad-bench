from __future__ import annotations

from .base import BaseModel, SolveResult
from .common import SYSTEM_PROMPT, env, error_result, price_for, require_env, safe_dict, timed


# USD per 1M tokens: input, output.
PRICES_USD_PER_1M = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "o3": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
}


class GPTModel(BaseModel):
    def __init__(self, model: str | None = None) -> None:
        self._model = model or env("OPENAI_MODEL", "gpt-4o")

    @property
    def model_id(self) -> str:
        return self._model

    def solve(self, problem: str) -> SolveResult:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=require_env("OPENAI_API_KEY"))

            response, latency_ms = timed(
                lambda: client.chat.completions.create(
                    model=self.model_id,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": problem},
                    ],
                )
            )

            usage = response.usage
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            input_per_1m, output_per_1m = price_for(
                self.model_id, PRICES_USD_PER_1M, PRICES_USD_PER_1M["gpt-4o"]
            )
            cost_usd = (
                prompt_tokens * input_per_1m / 1_000_000
                + completion_tokens * output_per_1m / 1_000_000
            )

            return SolveResult(
                model=self.model_id,
                answer=response.choices[0].message.content or "",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=round(cost_usd, 8),
                latency_ms=latency_ms,
                raw_response=safe_dict(response),
            )
        except Exception as exc:
            return error_result(self.model_id, exc)
