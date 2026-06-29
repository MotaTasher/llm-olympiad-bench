from __future__ import annotations

from typing import Any

from models.common import SYSTEM_PROMPT
from models.pricing import estimate_cost, estimate_tokens, token_price
from scoring.repository import PROVIDER_LABELS


DEFAULT_CALCULATOR_MAX_TOKENS = 4096
DEFAULT_CALCULATOR_RUNS = 1
MAX_CALCULATOR_TOKENS = 32000
MAX_CALCULATOR_RUNS = 1000


def bounded_int(value: str | int | None, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value not in {None, ""} else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def calculator_inputs(args: Any) -> dict[str, int]:
    return {
        "max_tokens": bounded_int(
            args.get("max_tokens"),
            DEFAULT_CALCULATOR_MAX_TOKENS,
            minimum=1,
            maximum=MAX_CALCULATOR_TOKENS,
        ),
        "runs": bounded_int(
            args.get("runs"),
            DEFAULT_CALCULATOR_RUNS,
            minimum=1,
            maximum=MAX_CALCULATOR_RUNS,
        ),
    }


def money(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 100:
        return f"{value:,.0f}"
    if value >= 1:
        return f"{value:,.2f}"
    return f"{value:,.4f}"


def selected_problems(competition: dict[str, Any], problem_id: str | None = None) -> list[dict[str, Any]]:
    if problem_id:
        problem = competition.get("problems", {}).get(problem_id)
        return [problem] if problem else []
    return [
        competition["problems"][item]
        for item in competition.get("problem_order", [])
        if item in competition.get("problems", {})
    ]


def build_cost_calculator(
    competition: dict[str, Any],
    *,
    max_tokens: int,
    runs: int,
    problem_id: str | None = None,
) -> dict[str, Any]:
    problems = selected_problems(competition, problem_id)
    system_tokens = estimate_tokens(SYSTEM_PROMPT)
    rows = []
    provider_totals: dict[str, dict[str, Any]] = {}

    for model in competition.get("model_columns", []):
        provider = str(model.get("provider") or "unknown")
        model_id = str(model.get("model_id") or model.get("label") or "unknown")
        prompt_tokens = sum(
            system_tokens + estimate_tokens(str(problem.get("statement") or ""))
            for problem in problems
        ) * runs
        completion_tokens = max_tokens * len(problems) * runs
        cost = estimate_cost(
            provider,
            model_id,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )
        native = cost.get("native") if isinstance(cost.get("native"), dict) else None
        total = cost.get("total")
        native_total = native.get("total") if native else None
        native_currency = native.get("currency") if native else None
        price = token_price(provider, model_id)
        row = {
            **model,
            "provider_label": PROVIDER_LABELS.get(provider, provider),
            "problem_count": len(problems),
            "runs": runs,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost": cost,
            "usd_total": total,
            "usd_display": money(total),
            "native_total": native_total,
            "native_currency": native_currency,
            "native_display": (
                f"{money(float(native_total))} {native_currency}"
                if native_total is not None and native_currency
                else None
            ),
            "pricing_note": cost.get("note") or (price.note if price else None),
        }
        rows.append(row)

        provider_total = provider_totals.setdefault(
            provider,
            {
                "provider": provider,
                "provider_label": PROVIDER_LABELS.get(provider, provider),
                "usd_total": 0.0,
                "native_totals": {},
            },
        )
        if isinstance(total, (int, float)):
            provider_total["usd_total"] += float(total)
        if native_total is not None and native_currency:
            provider_total["native_totals"][native_currency] = (
                provider_total["native_totals"].get(native_currency, 0.0) + float(native_total)
            )

    for total in provider_totals.values():
        total["usd_display"] = money(total["usd_total"])
        total["native_display"] = ", ".join(
            f"{money(value)} {currency}"
            for currency, value in sorted(total["native_totals"].items())
        )

    return {
        "max_tokens": max_tokens,
        "runs": runs,
        "problem_count": len(problems),
        "system_tokens": system_tokens,
        "rows": rows,
        "provider_totals": sorted(provider_totals.values(), key=lambda item: item["provider_label"]),
        "usd_total": sum(float(row["usd_total"] or 0.0) for row in rows),
        "usd_total_display": money(sum(float(row["usd_total"] or 0.0) for row in rows)),
    }
