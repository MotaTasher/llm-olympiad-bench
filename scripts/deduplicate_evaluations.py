from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.telemetry import atomic_write_json  # noqa: E402
from scoring.repository import deduplicate_evaluations, utc_now  # noqa: E402


def deduplicate_payload(payload: dict[str, Any]) -> int:
    pool = payload.get("evaluation_pool")
    if not isinstance(pool, dict):
        return 0
    removed = 0
    snapshots = payload.get("evaluations")
    if not isinstance(snapshots, dict):
        snapshots = {}
        payload["evaluations"] = snapshots
    for result_id, values in list(pool.items()):
        if not isinstance(values, list):
            continue
        kept = deduplicate_evaluations([item for item in values if isinstance(item, dict)])
        removed += len(values) - len(kept)
        pool[result_id] = kept
        if kept:
            snapshots[result_id] = {key: value for key, value in kept[-1].items() if not str(key).startswith("_")}
        else:
            snapshots.pop(result_id, None)
    if removed:
        payload["updated_at"] = utc_now()
    return removed


def migrate(results_dir: Path, *, apply: bool) -> tuple[int, int]:
    changed_files = 0
    removed_records = 0
    for path in sorted(results_dir.rglob("*.json")) if results_dir.exists() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        removed = deduplicate_payload(payload)
        if not removed:
            continue
        changed_files += 1
        removed_records += removed
        if apply:
            atomic_write_json(path, payload)
    return changed_files, removed_records


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep the latest evaluation per reviewer and result.")
    parser.add_argument("results_dir", nargs="?", type=Path, default=Path("data/results"))
    parser.add_argument("--apply", action="store_true", help="write changes; otherwise only report")
    args = parser.parse_args()
    files, records = migrate(args.results_dir, apply=args.apply)
    mode = "Updated" if args.apply else "Would update"
    print(f"{mode} {files} files; remove {records} duplicate evaluations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
