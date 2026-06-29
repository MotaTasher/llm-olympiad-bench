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
from ..pricing import DEEPSEEK_USD_PER_1M as PRICES_USD_PER_1M, estimate_cost, price_for
from ..telemetry import sanitized_base_url
from .versions import DEFAULT as DEFAULT_VERSION


class DeepSeekModel(BaseModel):
    def __init__(self, model: str | None = None) -> None:
        self._model = model or env("DEEPSEEK_MODEL", DEFAULT_VERSION)

    @property
    def model_id(self) -> str:
        return self._model

    def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult:
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=require_env("DEEPSEEK_API_KEY"),
                base_url=env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            )

            kwargs = {}
            if self.model_id not in {"deepseek-reasoner"}:
                kwargs["temperature"] = float(env("DEEPSEEK_TEMPERATURE", "0.3") or "0.3")
            configured_max = max_tokens or (
                int(env("DEEPSEEK_MAX_TOKENS", "4096") or "4096")
                if env("DEEPSEEK_MAX_TOKENS") is not None
                else None
            )
            if configured_max is not None:
                kwargs["max_tokens"] = configured_max
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": problem},
            ]
            base_url = env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            request_payload = {
                "model": self.model_id,
                "messages": messages,
                **kwargs,
                "endpoint": sanitized_base_url(f"{base_url}/chat/completions"),
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
                self.model_id, PRICES_USD_PER_1M, PRICES_USD_PER_1M[DEFAULT_VERSION]
            )
            cost_usd = (
                prompt_tokens * input_per_1m / 1_000_000
                + completion_tokens * output_per_1m / 1_000_000
            )
            cost = estimate_cost(
                "deepseek",
                self.model_id,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
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
                provider="deepseek",
                requested_model_id=self.model_id,
                resolved_model_id=raw_response.get("model") or self.model_id,
                request=request_payload,
                cost={**cost, "cached_input": None, "reasoning": None},
            )
        except Exception as exc:
            return error_result(self.model_id, exc)
