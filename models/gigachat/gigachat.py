from __future__ import annotations

import base64

from ..base import BaseModel, SolveResult
from ..common import SYSTEM_PROMPT, env, error_result, safe_dict, timed
from .versions import DEFAULT as DEFAULT_VERSION


class GigaChatModel(BaseModel):
    def __init__(self, model: str | None = None) -> None:
        self._model = model or env("GIGACHAT_MODEL", DEFAULT_VERSION)

    @property
    def model_id(self) -> str:
        return self._model

    def _credentials(self) -> str:
        credentials = env("GIGACHAT_CREDENTIALS")
        if credentials:
            return credentials
        client_id = env("GIGACHAT_CLIENT_ID")
        client_secret = env("GIGACHAT_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise RuntimeError(
                "Missing GIGACHAT_CREDENTIALS or both GIGACHAT_CLIENT_ID and "
                "GIGACHAT_CLIENT_SECRET. Put them in models/gigachat/secrets/.env"
            )
        return base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")

    def solve(self, problem: str) -> SolveResult:
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

            response, latency_ms = timed(
                lambda: client.chat(
                    {
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": problem},
                        ]
                    }
                )
            )

            usage = getattr(response, "usage", None)
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            answer = response.choices[0].message.content or ""

            return SolveResult(
                model=self.model_id,
                answer=answer,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=0.0,
                latency_ms=latency_ms,
                raw_response=safe_dict(response),
            )
        except Exception as exc:
            return error_result(self.model_id, exc)
