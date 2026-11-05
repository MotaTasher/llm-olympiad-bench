"""Versioned competition cohorts; independent of adapters' moving defaults."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROSTERS_DIR = Path(__file__).resolve().parents[1] / "config/model_rosters"
PROVIDERS = {"anthropic", "deepseek", "google", "gigachat", "xai", "zai", "openai", "yandexgpt", "kimi"}


def load_roster(roster_id: str, *, directory: Path | None = None) -> dict[str, Any]:
    if not isinstance(roster_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", roster_id):
        raise ValueError("Invalid model roster ID")
    path = (directory or ROSTERS_DIR) / (roster_id + ".json")
    try:
        roster = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot load model roster {roster_id}") from exc
    if (not isinstance(roster, dict) or roster.get("schema_version") != 1
            or roster.get("id") != roster_id or not isinstance(roster.get("models"), list)
            or not roster["models"] or not isinstance(roster.get("as_of"), str)):
        raise ValueError(f"Invalid model roster {roster_id}")
    seen = set()
    for model in roster["models"]:
        if not isinstance(model, dict):
            raise ValueError(f"Invalid model entry in {roster_id}")
        provider, model_id = model.get("provider"), model.get("model_id")
        if provider not in PROVIDERS or not isinstance(model_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", model_id):
            raise ValueError(f"Invalid model specification in {roster_id}")
        key = f"{provider}:{model_id}"
        if key in seen or not str(model.get("display_name") or "").strip():
            raise ValueError(f"Duplicate model or missing display name in {roster_id}")
        seen.add(key)
    return roster


def roster_for_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    roster_id = (metadata or {}).get("model_roster")
    return load_roster(roster_id) if roster_id is not None else None


def roster_specs(roster: dict[str, Any]) -> list[str]:
    return [f'{model["provider"]}:{model["model_id"]}' for model in roster["models"]]
