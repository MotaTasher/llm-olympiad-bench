from __future__ import annotations

from ..base import BaseModel, SolveResult
from ..common import SYSTEM_PROMPT, env, error_result, price_for, require_env, safe_dict, timed
from .versions import DEFAULT as DEFAULT_VERSION


# USD per 1M tokens: input cache miss, output.
PRICES_USD_PER_1M = {
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v4-pro": (0.435, 0.87),
    "deepseek-chat": (0.14, 0.28),
    "deepseek-reasoner": (0.14, 0.28),
}


class DeepSeekModel(BaseModel):
    def __init__(self, model: str | None = None) -> None:
        self._model = model or env("DEEPSEEK_MODEL", DEFAULT_VERSION)

    @property
    def model_id(self) -> str:
        return self._model

    def solve(self, problem: str) -> SolveResult:
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=require_env("DEEPSEEK_API_KEY"),
                base_url=env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            )

            kwargs = {}
            if self.model_id not in {"deepseek-reasoner"}:
                kwargs["temperature"] = float(env("DEEPSEEK_TEMPERATURE", "0.3") or "0.3")

            response, latency_ms = timed(
                lambda: client.chat.completions.create(
                    model=self.model_id,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": problem},
                    ],
                    **kwargs,
                )
            )

            usage = response.usage
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            input_per_1m, output_per_1m = price_for(
                self.model_id, PRICES_USD_PER_1M, PRICES_USD_PER_1M[DEFAULT_VERSION]
            )
            cost_usd = (
                prompt_tokens * input_per_1m / 1_000_000
                + completion_tokens * output_per_1m / 1_000_000
            )

            message = response.choices[0].message
            answer = message.content or ""
            reasoning = getattr(message, "reasoning_content", None)
            raw_response = safe_dict(response)
            if reasoning:
                raw_response["reasoning_content"] = reasoning

            return SolveResult(
                model=self.model_id,
                answer=answer,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=round(cost_usd, 8),
                latency_ms=latency_ms,
                raw_response=raw_response,
            )
        except Exception as exc:
            return error_result(self.model_id, exc)
