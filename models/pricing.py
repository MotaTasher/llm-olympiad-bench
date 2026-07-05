from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any


PRICING_VERSION = "2026-07-05"
DEFAULT_RUB_PER_USD = 90.0


@dataclass(frozen=True)
class TokenPrice:
    provider: str
    model_id: str
    currency: str
    input_per_1m: float | None = None
    output_per_1m: float | None = None
    total_per_1k: float | None = None
    source: str = "models/pricing.py"
    note: str | None = None


OPENAI_USD_PER_1M = {
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "o3": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
}

ANTHROPIC_USD_PER_1M = {
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-5": (5.00, 25.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

DEEPSEEK_USD_PER_1M = {
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v4-pro": (0.435, 0.87),
    "deepseek-chat": (0.14, 0.28),
    "deepseek-reasoner": (0.14, 0.28),
}

YANDEX_RUB_PER_1K = {
    "yandexgpt-5.1": 0.80,
    "yandexgpt-5-lite": 0.20,
    "yandexgpt-5-pro/latest": 0.80,
    "yandexgpt-5.1/latest": 0.80,
    "yandexgpt-5-lite/latest": 0.20,
    "aliceai-llm/latest": 0.80,
    "yandexgpt": 0.80,
    "yandexgpt-pro": 0.80,
    "yandexgpt-lite": 0.20,
    "yandexgpt-pro-32k": 1.20,
}

GIGACHAT_RUB_PER_1K = {
    "gigachat": 0.065,
    "gigachat-2": 0.065,
    "gigachat-pro": 0.50,
    "gigachat-2-pro": 0.50,
    "gigachat-max": 0.65,
    "gigachat-2-max": 0.65,
}


def rub_per_usd() -> float:
    try:
        value = float(os.environ.get("RUB_PER_USD") or DEFAULT_RUB_PER_USD)
    except ValueError:
        return DEFAULT_RUB_PER_USD
    return value if value > 0 else DEFAULT_RUB_PER_USD


def price_for(model_id: str, prices: dict[str, tuple[float, float]], fallback: tuple[float, float]) -> tuple[float, float]:
    normalized = model_id.lower()
    if normalized in prices:
        return prices[normalized]
    for prefix, price in prices.items():
        if normalized.startswith(prefix):
            return price
    return fallback


def total_price_for(model_id: str, prices: dict[str, float], fallback: float) -> float:
    normalized = model_id.lower()
    if normalized in prices:
        return prices[normalized]
    for prefix, price in prices.items():
        if normalized.startswith(prefix):
            return price
    return fallback


def token_price(provider: str, model_id: str) -> TokenPrice | None:
    provider = provider.lower()
    if provider == "openai":
        input_price, output_price = price_for(model_id, OPENAI_USD_PER_1M, OPENAI_USD_PER_1M["gpt-5.5"])
        return TokenPrice(provider, model_id, "USD", input_price, output_price)
    if provider == "anthropic":
        input_price, output_price = price_for(
            model_id,
            ANTHROPIC_USD_PER_1M,
            ANTHROPIC_USD_PER_1M["claude-opus-4-8"],
        )
        return TokenPrice(provider, model_id, "USD", input_price, output_price)
    if provider == "deepseek":
        input_price, output_price = price_for(
            model_id,
            DEEPSEEK_USD_PER_1M,
            DEEPSEEK_USD_PER_1M["deepseek-v4-pro"],
        )
        return TokenPrice(provider, model_id, "USD", input_price, output_price)
    if provider == "yandexgpt":
        return TokenPrice(
            provider,
            model_id,
            "RUB",
            total_per_1k=total_price_for(model_id, YANDEX_RUB_PER_1K, 0.80),
        )
    if provider == "gigachat":
        return TokenPrice(
            provider,
            model_id,
            "RUB",
            total_per_1k=total_price_for(model_id, GIGACHAT_RUB_PER_1K, 0.65),
            note="GigaChat text-generation package price; freemium tokens are not subtracted.",
        )
    return None


def estimate_tokens(text: str) -> int:
    compact_length = len((text or "").strip())
    return max(1, math.ceil(compact_length / 4))


def estimate_cost(
    provider: str,
    model_id: str,
    *,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int | None = None,
) -> dict[str, Any]:
    price = token_price(provider, model_id)
    if not price:
        return {
            "currency": "USD",
            "input": None,
            "output": None,
            "native": None,
            "total": None,
            "pricing_source": None,
            "pricing_version": PRICING_VERSION,
            "estimated": True,
            "exchange_rate": None,
            "note": "No pricing configured.",
        }

    if price.currency == "USD":
        input_cost = input_tokens * float(price.input_per_1m or 0) / 1_000_000
        output_cost = output_tokens * float(price.output_per_1m or 0) / 1_000_000
        reasoning_cost = (
            reasoning_tokens * float(price.output_per_1m or 0) / 1_000_000
            if reasoning_tokens is not None
            else None
        )
        return {
            "currency": "USD",
            "input": round(input_cost, 8),
            "output": round(output_cost, 8),
            "reasoning": round(reasoning_cost, 8) if reasoning_cost is not None else None,
            "native": None,
            "total": round(input_cost + output_cost, 8),
            "pricing_source": price.source,
            "pricing_version": PRICING_VERSION,
            "estimated": True,
            "exchange_rate": None,
            "note": price.note,
        }

    native_total = ((input_tokens + output_tokens) / 1000) * float(price.total_per_1k or 0)
    usd_total = native_total / rub_per_usd()
    native_reasoning = (
        (reasoning_tokens / 1000) * float(price.total_per_1k or 0)
        if reasoning_tokens is not None
        else None
    )
    return {
        "currency": "USD",
        "input": None,
        "output": None,
        "reasoning": round(native_reasoning / rub_per_usd(), 8) if native_reasoning is not None else None,
        "native": {
            "currency": price.currency,
            "total": round(native_total, 8),
            "reasoning": round(native_reasoning, 8) if native_reasoning is not None else None,
            "price_per_1k_total_tokens": price.total_per_1k,
        },
        "total": round(usd_total, 8),
        "pricing_source": price.source,
        "pricing_version": PRICING_VERSION,
        "estimated": True,
        "exchange_rate": {"RUB_PER_USD": rub_per_usd()},
        "note": price.note,
    }
