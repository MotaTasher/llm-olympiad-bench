from __future__ import annotations

import requests

from .base import BaseModel, SolveResult
from .common import SYSTEM_PROMPT, env, error_result, safe_dict, timed


# Approximate RUB pricing per 1000 total tokens. USD conversion is controlled by RUB_PER_USD.
PRICES_RUB_PER_1K = {
    "yandexgpt": 0.80,
    "yandexgpt-pro": 0.80,
    "yandexgpt-lite": 0.20,
    "yandexgpt-pro-32k": 1.20,
}


class YandexGPTModel(BaseModel):
    def __init__(self, model: str | None = None) -> None:
        self._model = model or env("YANDEX_MODEL", "yandexgpt")

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

            payload = {
                "modelUri": f"gpt://{folder_id}/{self.model_id}",
                "completionOptions": {
                    "stream": False,
                    "temperature": float(env("YANDEX_TEMPERATURE", "0.3") or "0.3"),
                    "maxTokens": int(env("YANDEX_MAX_TOKENS", "4000") or "4000"),
                },
                "messages": [
                    {"role": "system", "text": SYSTEM_PROMPT},
                    {"role": "user", "text": problem},
                ],
            }

            response, latency_ms = timed(
                lambda: requests.post(
                    "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                    headers=headers,
                    json=payload,
                    timeout=int(env("YANDEX_TIMEOUT", "120") or "120"),
                )
            )
            response.raise_for_status()
            data = response.json()
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
