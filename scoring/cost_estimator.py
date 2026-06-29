from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any
from urllib.request import urlopen
import xml.etree.ElementTree as ET

import runner
from models.common import SYSTEM_PROMPT, price_for


REASONING_BUDGET_MIN = 0
REASONING_BUDGET_MAX = 64000
REASONING_BUDGET_DEFAULT = 8000
FINAL_TOKENS_MIN = 512
FINAL_TOKENS_MAX = 32000
FINAL_TOKENS_DEFAULT = 8000
APPROX_CHARS_PER_TOKEN = 4
DEFAULT_USD_RUB_RATE = 90.0
CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

_rate_cache: dict[str, Any] = {}


def cost_context(competitions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "defaults": {
            "reasoningBudget": REASONING_BUDGET_DEFAULT,
            "reasoningMin": REASONING_BUDGET_MIN,
            "reasoningMax": REASONING_BUDGET_MAX,
            "finalTokens": FINAL_TOKENS_DEFAULT,
            "finalMin": FINAL_TOKENS_MIN,
            "finalMax": FINAL_TOKENS_MAX,
        },
        "exchangeRate": usd_rub_rate(),
        "models": model_pricing(),
        "competitions": [competition_cost_data(competition) for competition in competitions],
    }


def usd_rub_rate() -> dict[str, Any]:
    now = datetime.now(UTC)
    cached_at = _rate_cache.get("fetched_at")
    if isinstance(cached_at, datetime) and now - cached_at < timedelta(hours=6):
        return dict(_rate_cache["value"])
    try:
        with urlopen(CBR_DAILY_URL, timeout=2) as response:
            payload = response.read()
        root = ET.fromstring(payload)
        for valute in root.findall("Valute"):
            char_code = valute.findtext("CharCode")
            if char_code != "USD":
                continue
            nominal = float((valute.findtext("Nominal") or "1").replace(",", "."))
            value = float((valute.findtext("Value") or "").replace(",", "."))
            rate = value / nominal
            result = {
                "usdRub": rate,
                "source": CBR_DAILY_URL,
                "asOf": root.attrib.get("Date") or now.date().isoformat(),
                "fallback": False,
            }
            _rate_cache["fetched_at"] = now
            _rate_cache["value"] = result
            return result
    except Exception:
        pass
    result = {
        "usdRub": DEFAULT_USD_RUB_RATE,
        "source": CBR_DAILY_URL,
        "asOf": now.date().isoformat(),
        "fallback": True,
    }
    _rate_cache["fetched_at"] = now
    _rate_cache["value"] = result
    return result


def competition_cost_data(competition: dict[str, Any]) -> dict[str, Any]:
    solved = solved_pairs(competition)
    models: dict[str, dict[str, Any]] = {}
    for alias in runner.active_model_specs():
        models[alias] = {
            "model": alias,
            "pairs": 0,
            "solvedPairs": 0,
            "inputTokens": 0,
            "unsolvedInputTokens": 0,
        }
    for problem_id in competition.get("problem_order", []):
        problem = competition["problems"][problem_id]
        input_tokens = approximate_tokens(
            f"{SYSTEM_PROMPT}\n\n{problem.get('statement') or ''}"
        )
        for alias, data in models.items():
            data["pairs"] += 1
            data["inputTokens"] += input_tokens
            if (problem_id, alias) in solved:
                data["solvedPairs"] += 1
            else:
                data["unsolvedInputTokens"] += input_tokens
    return {
        "competitionId": competition.get("competition_id"),
        "models": list(models.values()),
    }


def approximate_tokens(text: str) -> int:
    return max(1, ceil(len(text) / APPROX_CHARS_PER_TOKEN))


def solved_pairs(competition: dict[str, Any]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for problem_id in competition.get("problem_order", []):
        problem = competition["problems"][problem_id]
        for state in problem.get("model_states", []):
            if any(attempt.get("successful_answer") for attempt in state.get("attempts", [])):
                pairs.add((problem_id, state["model_key"]))
    return pairs


def model_pricing() -> dict[str, dict[str, Any]]:
    rate = usd_rub_rate()["usdRub"]
    pricing = {}
    for alias in runner.active_model_specs():
        provider, _, model_id = alias.partition(":")
        pricing[alias] = model_price(provider, model_id, rate)
    return pricing


def model_price(provider: str, model_id: str, usd_rub: float) -> dict[str, Any]:
    if provider == "openai":
        from models.gpt.gpt import PRICES_USD_PER_1M

        input_per_1m, output_per_1m = price_for(
            model_id,
            PRICES_USD_PER_1M,
            PRICES_USD_PER_1M["gpt-4o"],
        )
        return usd_price(input_per_1m, output_per_1m, "models/gpt/gpt.py")
    if provider == "anthropic":
        from models.claude.claude import PRICES_USD_PER_1M

        input_per_1m, output_per_1m = price_for(
            model_id,
            PRICES_USD_PER_1M,
            PRICES_USD_PER_1M["claude-opus-4-5"],
        )
        return usd_price(input_per_1m, output_per_1m, "models/claude/claude.py")
    if provider == "deepseek":
        from models.deepseek.deepseek import PRICES_USD_PER_1M
        from models.deepseek.versions import DEFAULT

        input_per_1m, output_per_1m = price_for(
            model_id,
            PRICES_USD_PER_1M,
            PRICES_USD_PER_1M[DEFAULT],
        )
        return usd_price(input_per_1m, output_per_1m, "models/deepseek/deepseek.py")
    if provider == "yandexgpt":
        from models.yandexgpt.yandexgpt import PRICES_RUB_PER_1K

        rub_per_1k = PRICES_RUB_PER_1K.get(model_id.lower(), 0.80)
        usd_per_1m = rub_per_1k * 1000 / usd_rub
        return {
            "known": True,
            "mode": "total",
            "inputUsdPer1M": usd_per_1m,
            "outputUsdPer1M": usd_per_1m,
            "source": "models/yandexgpt/yandexgpt.py",
        }
    return {
        "known": False,
        "mode": "unknown",
        "inputUsdPer1M": None,
        "outputUsdPer1M": None,
        "source": None,
    }


def usd_price(input_per_1m: float, output_per_1m: float, source: str) -> dict[str, Any]:
    return {
        "known": True,
        "mode": "split",
        "inputUsdPer1M": input_per_1m,
        "outputUsdPer1M": output_per_1m,
        "source": source,
    }
