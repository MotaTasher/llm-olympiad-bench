from __future__ import annotations

import base64
import binascii

from ..base import BaseModel, SolveResult
from ..common import SYSTEM_PROMPT, empty_answer_error, ensure_text_only_request, env, error_result, safe_dict, timed
from ..pricing import estimate_cost
from ..telemetry import sanitized_base_url
from .versions import DEFAULT as DEFAULT_VERSION


def normalize_gigachat_credentials(credentials: str) -> str:
    value = credentials.strip()
    if value.lower().startswith("basic "):
        value = value.split(None, 1)[1].strip()
    if value.lower().startswith("base64(") and value.endswith(")"):
        value = value[7:-1].strip()

    if ":" in value:
        return base64.b64encode(value.encode("utf-8")).decode("ascii")

    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError(
            "Invalid GIGACHAT_CREDENTIALS: expected Base64(client_id:client_secret), "
            "raw client_id:client_secret, or GIGACHAT_CLIENT_ID + GIGACHAT_CLIENT_SECRET"
        ) from exc

    if b":" not in decoded:
        raise RuntimeError(
            "Invalid GIGACHAT_CREDENTIALS: decoded value must look like "
            "client_id:client_secret"
        )
    return value


def build_gigachat_credentials(client_id: str, client_secret: str) -> str:
    value = f"{client_id.strip()}:{client_secret.strip()}"
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


class GigaChatModel(BaseModel):
    def __init__(
        self,
        model: str | None = None,
        *,
        reasoning_budget_tokens: int | None = None,
        max_final_tokens: int | None = None,
    ) -> None:
        self._model = model or env("GIGACHAT_MODEL", DEFAULT_VERSION)
        self._reasoning_budget_tokens = reasoning_budget_tokens
        self._max_final_tokens = max_final_tokens

    @property
    def model_id(self) -> str:
        return self._model

    def _credentials(self) -> str:
        client_id = env("GIGACHAT_CLIENT_ID")
        client_secret = env("GIGACHAT_CLIENT_SECRET")
        if client_id and client_secret:
            return build_gigachat_credentials(client_id, client_secret)

        credentials = env("GIGACHAT_CREDENTIALS")
        if credentials:
            return normalize_gigachat_credentials(credentials)

        raise RuntimeError(
            "Missing GIGACHAT_CREDENTIALS or both GIGACHAT_CLIENT_ID and "
            "GIGACHAT_CLIENT_SECRET. Put them in models/gigachat/secrets/.env"
        )

    def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult:
        try:
            from gigachat import GigaChat

            verify_ssl = (env("GIGACHAT_VERIFY_SSL", "false") or "false").lower() in {
                "1",
                "true",
                "yes",
            }
            client = GigaChat(
                credentials=self._credentials(),
                scope=env("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
                model=self.model_id,
                verify_ssl_certs=verify_ssl,
            )

            payload = {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": problem},
                ]
            }
            if env("GIGACHAT_TEMPERATURE") is not None:
                payload["temperature"] = float(env("GIGACHAT_TEMPERATURE", "0.1") or "0.1")
            if env("GIGACHAT_TOP_P") is not None:
                payload["top_p"] = float(env("GIGACHAT_TOP_P", "0.9") or "0.9")
            if max_tokens is not None:
                payload["max_tokens"] = int(max_tokens)
            elif self._max_final_tokens is not None:
                payload["max_tokens"] = int(self._max_final_tokens)
            elif env("GIGACHAT_MAX_TOKENS") is not None:
                payload["max_tokens"] = int(env("GIGACHAT_MAX_TOKENS", "4096") or "4096")
            if env("GIGACHAT_REPETITION_PENALTY") is not None:
                payload["repetition_penalty"] = float(
                    env("GIGACHAT_REPETITION_PENALTY", "1.05") or "1.05"
                )
            request_payload = {
                "model": self.model_id,
                **payload,
                "endpoint": sanitized_base_url("https://gigachat.devices.sberbank.ru/api/v1/chat/completions"),
                "stream": False,
            }
            ensure_text_only_request(request_payload)

            response, latency_ms = timed(
                lambda: client.chat(payload)
            )

            usage = getattr(response, "usage", None)
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            answer = response.choices[0].message.content or ""
            raw_response = safe_dict(response)
            finish = None
            choices = raw_response.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                finish = choices[0].get("finish_reason") or choices[0].get("finishReason")
            cost = estimate_cost(
                "gigachat",
                self.model_id,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
            )
            error = None
            if not answer.strip():
                error = empty_answer_error(
                    "GigaChat API",
                    generated_tokens=completion_tokens,
                    finish_reason=str(finish) if finish else None,
                )

            return SolveResult(
                model=self.model_id,
                answer=answer,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost.get("total") or 0.0,
                latency_ms=latency_ms,
                raw_response=raw_response,
                error=error,
                provider="gigachat",
                requested_model_id=self.model_id,
                resolved_model_id=raw_response.get("model") or self.model_id,
                request=request_payload,
                cost={**cost, "cached_input": None, "reasoning": None},
                finish_reason=str(finish) if finish else None,
            )
        except Exception as exc:
            result = error_result(self.model_id, exc)
            result.provider = "gigachat"
            result.requested_model_id = self.model_id
            result.resolved_model_id = self.model_id
            return result
