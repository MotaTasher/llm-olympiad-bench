from __future__ import annotations

from ..base import BaseModel, SolveResult
from ..common import (
    SYSTEM_PROMPT,
    empty_answer_error,
    ensure_text_only_request,
    env,
    error_result,
    safe_dict,
    timed,
)
from ..pricing import YANDEX_RUB_PER_1K as PRICES_RUB_PER_1K, estimate_cost
from ..telemetry import sanitized_base_url
from .versions import DEFAULT as DEFAULT_VERSION


class YandexGPTModel(BaseModel):
    def __init__(
        self,
        model: str | None = None,
        *,
        reasoning_budget_tokens: int | None = None,
        max_final_tokens: int | None = None,
    ) -> None:
        self._model = model or env("YANDEX_MODEL", DEFAULT_VERSION)
        self._reasoning_budget_tokens = reasoning_budget_tokens
        self._max_final_tokens = max_final_tokens

    @property
    def model_id(self) -> str:
        return self._model

    def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult:
        try:
            import requests

            folder_id = env("YANDEX_FOLDER_ID")
            if not folder_id:
                raise RuntimeError(
                    "Missing YANDEX_FOLDER_ID. Put it in models/yandexgpt/secrets/.env"
                )
            api_key = env("YANDEX_API_KEY")
            iam_token = env("YANDEX_IAM_TOKEN")
            if not api_key and not iam_token:
                raise RuntimeError(
                    "Missing YANDEX_API_KEY or YANDEX_IAM_TOKEN. "
                    "Put one of them in models/yandexgpt/secrets/.env"
                )

            headers = {
                "Content-Type": "application/json",
                "x-folder-id": folder_id,
            }
            if api_key:
                headers["Authorization"] = f"Api-Key {api_key}"
            else:
                headers["Authorization"] = f"Bearer {iam_token}"

            completion_options = {
                "stream": False,
                "temperature": float(env("YANDEX_TEMPERATURE", "0.15") or "0.15"),
                "maxTokens": (
                    int(max_tokens)
                    if max_tokens is not None
                    else int(self._max_final_tokens)
                    if self._max_final_tokens is not None
                    else int(env("YANDEX_MAX_TOKENS", "8000") or "8000")
                ),
            }
            reasoning_mode = env("YANDEX_REASONING_MODE")
            if reasoning_mode:
                completion_options["reasoningOptions"] = {"mode": reasoning_mode}

            payload = {
                "modelUri": f"gpt://{folder_id}/{self.model_id}",
                "completionOptions": completion_options,
                "messages": [
                    {"role": "system", "text": SYSTEM_PROMPT},
                    {"role": "user", "text": problem},
                ],
            }
            request_payload = {
                "model": self.model_id,
                "completionOptions": completion_options,
                "messages": payload["messages"],
                "endpoint": sanitized_base_url(
                    "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
                ),
                "stream": completion_options.get("stream"),
            }
            ensure_text_only_request(request_payload)

            def post_completion() -> requests.Response:
                return requests.post(
                    "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                    headers=headers,
                    json=payload,
                    timeout=int(env("YANDEX_TIMEOUT", "120") or "120"),
                )

            response, latency_ms = timed(post_completion)
            retried_without_reasoning = False
            if response.status_code == 400 and reasoning_mode:
                error_text = response.text.lower()
                if "reasoning" in error_text and "not support" in error_text:
                    payload["completionOptions"].pop("reasoningOptions", None)
                    response, retry_latency_ms = timed(post_completion)
                    latency_ms += retry_latency_ms
                    retried_without_reasoning = True
            response.raise_for_status()
            data = response.json()
            if retried_without_reasoning:
                data["_adapter_note"] = (
                    "YANDEX_REASONING_MODE was requested, but the selected model "
                    "does not support reasoning; retried without reasoningOptions."
                )
            result = data.get("result", {})
            usage = result.get("usage", {})
            prompt_tokens = int(usage.get("inputTextTokens") or usage.get("inputTokens") or 0)
            completion_tokens = int(usage.get("completionTokens") or 0)
            completion_details = usage.get("completionTokensDetails")
            if not isinstance(completion_details, dict):
                completion_details = {}
            try:
                reasoning_tokens = int(completion_details.get("reasoningTokens") or 0)
            except (TypeError, ValueError):
                reasoning_tokens = 0
            answer = (
                result.get("alternatives", [{}])[0]
                .get("message", {})
                .get("text", "")
            )

            total_tokens = prompt_tokens + completion_tokens
            price_rub_per_1k = PRICES_RUB_PER_1K.get(self.model_id.lower(), 0.80)
            rub_per_usd = float(env("RUB_PER_USD", "90") or "90")
            cost_usd = (total_tokens / 1000) * price_rub_per_1k / rub_per_usd
            cost = estimate_cost(
                "yandexgpt",
                self.model_id,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                reasoning_tokens=reasoning_tokens or None,
            )
            raw_response = safe_dict(data)
            alternatives = result.get("alternatives") if isinstance(result, dict) else None
            finish = None
            if isinstance(alternatives, list) and alternatives and isinstance(alternatives[0], dict):
                finish = alternatives[0].get("status") or alternatives[0].get("finishReason")
            error = None
            if not answer.strip():
                error = empty_answer_error(
                    "YandexGPT Completion API",
                    generated_tokens=completion_tokens + reasoning_tokens,
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
                provider="yandexgpt",
                requested_model_id=self.model_id,
                resolved_model_id=self.model_id,
                request=request_payload,
                usage={
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": usage.get("totalTokens") or total_tokens,
                    "reasoning_tokens": reasoning_tokens or None,
                    "cached_input_tokens": None,
                    "cache_creation_input_tokens": None,
                    "raw": raw_response.get("result", {}).get("usage") or {},
                    "source": "provider_response",
                },
                cost={**cost, "cached_input": None},
                finish_reason=str(finish) if finish else None,
            )
        except Exception as exc:
            result = error_result(self.model_id, exc)
            result.provider = "yandexgpt"
            result.requested_model_id = self.model_id
            result.resolved_model_id = self.model_id
            return result
