from __future__ import annotations

import requests

from ..base import BaseModel, SolveResult
from ..common import SYSTEM_PROMPT, env, error_result, safe_dict, timed
from .versions import DEFAULT as DEFAULT_VERSION


# Approximate RUB pricing per 1000 total tokens. USD conversion is controlled by RUB_PER_USD.
PRICES_RUB_PER_1K = {
    "yandexgpt-5-pro/latest": 0.80,
    "yandexgpt-5.1/latest": 0.80,
    "yandexgpt-5-lite/latest": 0.20,
    "aliceai-llm/latest": 0.80,
    "yandexgpt": 0.80,
    "yandexgpt-pro": 0.80,
    "yandexgpt-lite": 0.20,
    "yandexgpt-pro-32k": 1.20,
}


class YandexGPTModel(BaseModel):
    def __init__(self, model: str | None = None) -> None:
        self._model = model or env("YANDEX_MODEL", DEFAULT_VERSION)

    @property
    def model_id(self) -> str:
        return self._model

    def solve(self, problem: str) -> SolveResult:
        try:
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
                "maxTokens": int(env("YANDEX_MAX_TOKENS", "8000") or "8000"),
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
            answer = (
                result.get("alternatives", [{}])[0]
                .get("message", {})
                .get("text", "")
            )

            total_tokens = prompt_tokens + completion_tokens
            price_rub_per_1k = PRICES_RUB_PER_1K.get(self.model_id.lower(), 0.80)
            rub_per_usd = float(env("RUB_PER_USD", "90") or "90")
            cost_usd = (total_tokens / 1000) * price_rub_per_1k / rub_per_usd

            return SolveResult(
                model=self.model_id,
                answer=answer,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=round(cost_usd, 8),
                latency_ms=latency_ms,
                raw_response=safe_dict(data),
            )
        except Exception as exc:
            return error_result(self.model_id, exc)
