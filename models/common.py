from __future__ import annotations

import dataclasses
import json
import os
import time
from typing import Any, Callable

from .base import SolveResult
from .pricing import price_for
from .telemetry import redact, structured_error


FORBIDDEN_REQUEST_KEYS = {
    "tool_choice",
    "tools",
    "function_call",
    "functions",
    "web_search_options",
}


SYSTEM_PROMPT = (
    "Ты решаешь олимпиадные задачи строго и аккуратно. "
    "Сначала формализуй условие, введи обозначения и проверь все ограничения. "
    "Затем дай полное доказательство без скачков, перебора несуществующих случаев "
    "и неподтвержденных утверждений. Если используешь лемму, докажи ее. "
    "Не доказывай утверждение частным примером, если требуется доказательство для всех случаев. "
    "Перед финальным ответом проверь, что выбранные объекты действительно существуют при любых допустимых данных. "
    "В конце явно сформулируй финальный вывод. "
    "Не используй инструменты, поиск, код или калькуляторы."
)


def ensure_text_only_request(value: Any, path: str = "request") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = f"{path}.{key}"
            if key in FORBIDDEN_REQUEST_KEYS:
                raise RuntimeError(f"Text-only policy violation: {next_path} is forbidden")
            ensure_text_only_request(item, next_path)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            ensure_text_only_request(item, f"{path}[{index}]")


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def require_env(name: str) -> str:
    value = env(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def timed(call: Callable[[], Any]) -> tuple[Any, int]:
    start = time.monotonic()
    result = call()
    return result, int((time.monotonic() - start) * 1000)


def safe_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    for attr in ("model_dump", "dict"):
        method = getattr(value, attr, None)
        if callable(method):
            try:
                return redact(json.loads(json.dumps(method(), default=str)))
            except Exception:
                pass
    if dataclasses.is_dataclass(value):
        return redact(json.loads(json.dumps(dataclasses.asdict(value), default=str)))
    if isinstance(value, dict):
        return redact(json.loads(json.dumps(value, default=str)))
    return {"repr": repr(value)}


def error_result(model_id: str, error: Exception | str, latency_ms: int = 0) -> SolveResult:
    safe_error = str(redact(str(error)))
    return SolveResult(
        model=model_id,
        answer="",
        prompt_tokens=0,
        completion_tokens=0,
        cost_usd=0.0,
        latency_ms=latency_ms,
        raw_response={},
        error=safe_error,
        error_info=structured_error(error),
    )


def empty_answer_error(
    provider: str,
    *,
    generated_tokens: int | None = None,
    finish_reason: str | None = None,
    request_count: int | None = None,
) -> str:
    details = []
    if request_count is not None:
        details.append(f"{request_count} request(s)")
    if generated_tokens is not None:
        details.append(f"{generated_tokens} generated token(s)")
    if finish_reason:
        details.append(f"finish_reason={finish_reason}")
    suffix = f" after {', '.join(details)}" if details else ""
    return f"{provider} returned no visible output{suffix}"
