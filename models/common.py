from __future__ import annotations

import dataclasses
import json
import os
import time
from typing import Any, Callable

from .base import SolveResult


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
                return json.loads(json.dumps(method(), default=str))
            except Exception:
                pass
    if dataclasses.is_dataclass(value):
        return json.loads(json.dumps(dataclasses.asdict(value), default=str))
    if isinstance(value, dict):
        return json.loads(json.dumps(value, default=str))
    return {"repr": repr(value)}


def error_result(model_id: str, error: Exception | str, latency_ms: int = 0) -> SolveResult:
    return SolveResult(
        model=model_id,
        answer="",
        prompt_tokens=0,
        completion_tokens=0,
        cost_usd=0.0,
        latency_ms=latency_ms,
        raw_response={},
        error=str(error),
    )


def price_for(model_id: str, prices: dict[str, tuple[float, float]], fallback: tuple[float, float]) -> tuple[float, float]:
    normalized = model_id.lower()
    if normalized in prices:
        return prices[normalized]
    for prefix, price in prices.items():
        if normalized.startswith(prefix):
            return price
    return fallback
