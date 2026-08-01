from __future__ import annotations

from typing import Any

from ..base import BaseModel, SolveResult
from ..common import SYSTEM_PROMPT, empty_answer_error, ensure_text_only_request, env, error_result, require_env, timed
from ..pricing import estimate_cost
from ..telemetry import sanitized_base_url
from .versions import DEFAULT as DEFAULT_VERSION


KIMI_DEFAULT_BASE_URL = "https://api.moonshot.ai/v1"


class KimiModel(BaseModel):
    def __init__(self, model: str | None = None, *, reasoning_budget_tokens: int | None = None, max_final_tokens: int | None = None) -> None:
        self._model = model or env("KIMI_MODEL", DEFAULT_VERSION)
        self._reasoning_budget_tokens = reasoning_budget_tokens
        self._max_final_tokens = max_final_tokens

    @property
    def model_id(self) -> str:
        return self._model

    def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult:
        request_payload: dict[str, Any] = {}
        response_data: dict[str, Any] = {}
        latency_ms = 0
        try:
            import requests

            total_budget = int(max_tokens) if max_tokens is not None else int(self._max_final_tokens or env("KIMI_MAX_TOKENS", "256000"))
            temperature = float(env("KIMI_TEMPERATURE", "1") or "1")
            if self.model_id.startswith("kimi-k3") and temperature != 1:
                raise ValueError("Kimi K3 accepts only temperature=1")
            messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": problem}]
            request_payload = {
                "model": self.model_id, "messages": messages, "max_completion_tokens": total_budget,
                "temperature": temperature,
                "endpoint": sanitized_base_url(f"{env('KIMI_BASE_URL', KIMI_DEFAULT_BASE_URL)}/chat/completions"),
                "stream": False,
            }
            ensure_text_only_request(request_payload)
            response, latency_ms = timed(lambda: requests.post(
                f"{env('KIMI_BASE_URL', KIMI_DEFAULT_BASE_URL)}/chat/completions",
                headers={"Authorization": f"Bearer {require_env('KIMI_API_KEY')}", "Content-Type": "application/json"},
                json={key: request_payload[key] for key in ("model", "messages", "max_completion_tokens", "temperature", "stream")},
                timeout=int(env("KIMI_TIMEOUT_SECONDS", "7200") or "7200"),
            ))
            try:
                response_data = response.json()
            except ValueError:
                response_data = {"http_status": response.status_code, "body": response.text[:4096]}
            if not response.ok:
                api_error = response_data.get("error") if isinstance(response_data, dict) else None
                message = api_error.get("message") if isinstance(api_error, dict) else None
                raise RuntimeError(f"Moonshot Kimi API HTTP {response.status_code}: {message or 'unspecified error'}")
            data = response_data
            usage = data.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            completion_details = usage.get("completion_tokens_details") or {}
            prompt_details = usage.get("prompt_tokens_details") or {}
            reasoning_tokens = completion_details.get("reasoning_tokens")
            cached_input_tokens = prompt_details.get("cached_tokens")
            cost = estimate_cost(
                "kimi",
                self.model_id,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                reasoning_tokens=int(reasoning_tokens) if reasoning_tokens is not None else None,
                cached_input_tokens=int(cached_input_tokens) if cached_input_tokens is not None else None,
            )
            choice = (data.get("choices") or [{}])[0]
            answer = str((choice.get("message") or {}).get("content") or "")
            finish = choice.get("finish_reason")
            error = None if answer.strip() else empty_answer_error("Moonshot Kimi API", generated_tokens=completion_tokens, finish_reason=finish)
            return SolveResult(model=self.model_id, answer=answer, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, cost_usd=float(cost.get("total") or 0), latency_ms=latency_ms, raw_response=data, error=error, provider="kimi", requested_model_id=self.model_id, resolved_model_id=data.get("model") or self.model_id, request=request_payload, usage={"input_tokens": prompt_tokens, "output_tokens": completion_tokens, "reasoning_tokens": int(reasoning_tokens) if reasoning_tokens is not None else None, "cached_input_tokens": int(cached_input_tokens) if cached_input_tokens is not None else None, "total_tokens": int(usage.get("total_tokens") or prompt_tokens + completion_tokens), "source": "provider_response"}, cost=cost, finish_reason=finish)
        except Exception as exc:
            result = error_result(self.model_id, exc, latency_ms=latency_ms)
            result.provider = "kimi"
            result.requested_model_id = self.model_id
            result.resolved_model_id = self.model_id
            result.request = request_payload or None
            result.raw_response = response_data
            return result
