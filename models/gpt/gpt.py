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


class GPTModel(BaseModel):
    def __init__(self, model: str | None = None) -> None:
        self._model = model or env("OPENAI_MODEL", DEFAULT_VERSION)

    @property
    def model_id(self) -> str:
        return self._model

    def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=require_env("OPENAI_API_KEY"))
            kwargs = {}
            configured_max = max_tokens or (
                int(env("OPENAI_MAX_COMPLETION_TOKENS", "4096") or "4096")
                if env("OPENAI_MAX_COMPLETION_TOKENS") is not None
                else None
            )
            if configured_max is not None:
                kwargs["max_completion_tokens"] = configured_max
            if env("OPENAI_REASONING_EFFORT") is not None:
                kwargs["reasoning_effort"] = env("OPENAI_REASONING_EFFORT")
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": problem},
            ]
            request_payload = {
                "model": self.model_id,
                "messages": messages,
                **kwargs,
                "endpoint": sanitized_base_url("https://api.openai.com/v1/chat/completions"),
                "stream": False,
            }
            ensure_text_only_request(request_payload)

            response, latency_ms = timed(
                lambda: client.chat.completions.create(
                    model=self.model_id,
                    messages=messages,
                    **kwargs,
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
            cost = estimate_cost(
                "openai",
                self.model_id,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
            )
            raw_response = safe_dict(response)

            return SolveResult(
                model=self.model_id,
                answer=response.choices[0].message.content or "",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=round(cost_usd, 8),
                latency_ms=latency_ms,
                raw_response=raw_response,
                provider="openai",
                requested_model_id=self.model_id,
                resolved_model_id=raw_response.get("model") or self.model_id,
                request=request_payload,
                cost={**cost, "cached_input": None, "reasoning": None},
            )
        except Exception as exc:
            return error_result(self.model_id, exc)
