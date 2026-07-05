from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any
from urllib.request import urlopen
import xml.etree.ElementTree as ET

import runner
from models.common import SYSTEM_PROMPT, price_for

try:
    from .repository import canonical_model_key, infer_provider
except ImportError:  # pragma: no cover - direct `python scoring/app.py`
    from scoring.repository import canonical_model_key, infer_provider  # type: ignore


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
    exchange_rate = usd_rub_rate()
    rate = float(exchange_rate["usdRub"])
    competition_data = [competition_cost_data(competition, rate) for competition in competitions]
    return {
        "defaults": {
            "reasoningBudget": REASONING_BUDGET_DEFAULT,
            "reasoningMin": REASONING_BUDGET_MIN,
            "reasoningMax": REASONING_BUDGET_MAX,
            "finalTokens": FINAL_TOKENS_DEFAULT,
            "finalMin": FINAL_TOKENS_MIN,
            "finalMax": FINAL_TOKENS_MAX,
        },
        "exchangeRate": exchange_rate,
        "models": model_pricing(rate),
        "competitions": competition_data,
        "spent": total_spend(competition_data),
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


def competition_cost_data(competition: dict[str, Any], usd_rub: float) -> dict[str, Any]:
    solved = solved_pairs(competition)
    models: dict[str, dict[str, Any]] = {}
    for alias in runner.active_model_specs():
        models[alias] = {
            "model": alias,
            "pairs": 0,
            "solvedPairs": 0,
            "inputTokens": 0,
            "unsolvedInputTokens": 0,
            "spentUsd": 0.0,
            "spentResults": 0,
            "spentMissing": 0,
        }
    spent_all = empty_spend()
    spent_latest = empty_spend()
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
        for run in problem.get("runs", []):
            for result in run.get("results", []):
                if not isinstance(result, dict):
                    continue
                usd = result_cost_usd(result, usd_rub)
                add_result_cost(spent_all, usd)
                model_data = models.get(result_model_key(result))
                if model_data is None:
                    continue
                if usd is None:
                    model_data["spentMissing"] += 1
                else:
                    model_data["spentUsd"] += usd
                    model_data["spentResults"] += 1
        for state in problem.get("model_states", []):
            latest = state.get("latest")
            if not latest:
                continue
            add_result_cost(spent_latest, result_cost_usd(latest.get("result") or {}, usd_rub))
    return {
        "competitionId": competition.get("competition_id"),
        "models": list(models.values()),
        "spent": {
            "latestUsd": round(float(spent_latest["usd"]), 8),
            "latestResults": spent_latest["results"],
            "latestMissing": spent_latest["missing"],
            "allUsd": round(float(spent_all["usd"]), 8),
            "allResults": spent_all["results"],
            "allMissing": spent_all["missing"],
        },
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


def model_pricing(rate: float | None = None) -> dict[str, dict[str, Any]]:
    rate = float(rate if rate is not None else usd_rub_rate()["usdRub"])
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
        return usd_price(
            input_per_1m,
            output_per_1m,
            "models/gpt/gpt.py",
            reasoning_per_1m=output_per_1m,
            reasoning_label="output",
        )
    if provider == "anthropic":
        from models.claude.claude import PRICES_USD_PER_1M

        input_per_1m, output_per_1m = price_for(
            model_id,
            PRICES_USD_PER_1M,
            PRICES_USD_PER_1M["claude-opus-4-5"],
        )
        return usd_price(
            input_per_1m,
            output_per_1m,
            "models/claude/claude.py",
            reasoning_per_1m=output_per_1m,
            reasoning_label="output",
        )
    if provider == "deepseek":
        from models.deepseek.deepseek import PRICES_USD_PER_1M
        from models.deepseek.versions import DEFAULT

        input_per_1m, output_per_1m = price_for(
            model_id,
            PRICES_USD_PER_1M,
            PRICES_USD_PER_1M[DEFAULT],
        )
        reasoning_per_1m = output_per_1m if deepseek_reasoning_model(model_id) else None
        return usd_price(
            input_per_1m,
            output_per_1m,
            "models/deepseek/deepseek.py",
            reasoning_per_1m=reasoning_per_1m,
            reasoning_label="output" if reasoning_per_1m is not None else None,
        )
    if provider == "yandexgpt":
        from models.yandexgpt.yandexgpt import PRICES_RUB_PER_1K

        rub_per_1k = PRICES_RUB_PER_1K.get(model_id.lower(), 0.80)
        usd_per_1m = rub_per_1k * 1000 / usd_rub
        return {
            "known": True,
            "mode": "total",
            "inputUsdPer1M": usd_per_1m,
            "outputUsdPer1M": usd_per_1m,
            "reasoningUsdPer1M": usd_per_1m,
            "reasoningBilling": "total",
            "source": "models/yandexgpt/yandexgpt.py",
        }
    if provider == "gigachat":
        from models.pricing import GIGACHAT_RUB_PER_1K, total_price_for

        rub_per_1k = total_price_for(model_id, GIGACHAT_RUB_PER_1K, 0.65)
        usd_per_1m = rub_per_1k * 1000 / usd_rub
        return {
            "known": True,
            "mode": "total",
            "inputUsdPer1M": usd_per_1m,
            "outputUsdPer1M": usd_per_1m,
            "reasoningUsdPer1M": None,
            "reasoningBilling": None,
            "source": "models/pricing.py",
        }
    return {
        "known": False,
        "mode": "unknown",
        "inputUsdPer1M": None,
        "outputUsdPer1M": None,
        "reasoningUsdPer1M": None,
        "reasoningBilling": None,
        "source": None,
    }


def deepseek_reasoning_model(model_id: str) -> bool:
    normalized = model_id.lower()
    return normalized in {"deepseek-reasoner", "deepseek-v4-flash", "deepseek-v4-pro"}


def usd_price(
    input_per_1m: float,
    output_per_1m: float,
    source: str,
    *,
    reasoning_per_1m: float | None = None,
    reasoning_label: str | None = None,
) -> dict[str, Any]:
    return {
        "known": True,
        "mode": "split",
        "inputUsdPer1M": input_per_1m,
        "outputUsdPer1M": output_per_1m,
        "reasoningUsdPer1M": reasoning_per_1m,
        "reasoningBilling": reasoning_label,
        "source": source,
    }


def empty_spend() -> dict[str, float | int]:
    return {"usd": 0.0, "results": 0, "missing": 0}


def add_result_cost(spend: dict[str, float | int], usd: float | None) -> None:
    if usd is None:
        spend["missing"] = int(spend["missing"]) + 1
        return
    spend["usd"] = float(spend["usd"]) + usd
    spend["results"] = int(spend["results"]) + 1


def total_spend(competition_data: list[dict[str, Any]]) -> dict[str, Any]:
    latest_usd = 0.0
    all_usd = 0.0
    latest_results = 0
    all_results = 0
    latest_missing = 0
    all_missing = 0
    for competition in competition_data:
        spent = competition.get("spent") if isinstance(competition.get("spent"), dict) else {}
        latest_usd += float(spent.get("latestUsd") or 0.0)
        all_usd += float(spent.get("allUsd") or 0.0)
        latest_results += int(spent.get("latestResults") or 0)
        all_results += int(spent.get("allResults") or 0)
        latest_missing += int(spent.get("latestMissing") or 0)
        all_missing += int(spent.get("allMissing") or 0)
    return {
        "latestUsd": round(latest_usd, 8),
        "latestResults": latest_results,
        "latestMissing": latest_missing,
        "allUsd": round(all_usd, 8),
        "allResults": all_results,
        "allMissing": all_missing,
    }


def numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def result_cost_usd(result: dict[str, Any], usd_rub: float) -> float | None:
    cost = result.get("cost") if isinstance(result.get("cost"), dict) else {}
    total = numeric(cost.get("total"))
    currency = str(cost.get("currency") or "USD").upper()
    if total is not None:
        if currency == "USD":
            return total
        if currency == "RUB" and usd_rub > 0:
            return total / usd_rub

    native = cost.get("native") if isinstance(cost.get("native"), dict) else {}
    native_total = numeric(native.get("total"))
    native_currency = str(native.get("currency") or "").upper()
    if native_total is not None and native_currency == "RUB" and usd_rub > 0:
        return native_total / usd_rub

    return numeric(result.get("cost_usd"))


def result_model_key(result: dict[str, Any]) -> str:
    provider = str(result.get("provider") or infer_provider(str(result.get("model") or "")))
    model_id = str(result.get("requested_model_id") or result.get("model") or "unknown")
    return canonical_model_key(provider, model_id)
