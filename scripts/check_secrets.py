from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner import load_env


REQUIRED = {
    "gpt": {
        "all": [],
        "one_of": [("OPENAI_API_KEY",)],
    },
    "openai": {
        "all": [],
        "one_of": [("OPENAI_API_KEY",)],
    },
    "gigachat": {
        "all": [],
        "one_of": [
            ("GIGACHAT_CREDENTIALS",),
            ("GIGACHAT_CLIENT_ID", "GIGACHAT_CLIENT_SECRET"),
        ],
    },
    "yandexgpt": {
        "all": [("YANDEX_FOLDER_ID",)],
        "one_of": [("YANDEX_API_KEY",), ("YANDEX_IAM_TOKEN",)],
    },
}


def group_loaded(group: tuple[str, ...]) -> bool:
    return all(bool(os.environ.get(name)) for name in group)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check model-local secrets without printing values.")
    parser.add_argument(
        "--models",
        default="gpt,gigachat,yandexgpt",
        help="Comma-separated model aliases to check",
    )
    args = parser.parse_args()
    load_env()

    exit_code = 0
    for model in [item.strip().lower() for item in args.models.split(",") if item.strip()]:
        checks = REQUIRED.get(model)
        if not checks:
            print(f"{model}: no secret checks configured")
            continue
        ok = all(group_loaded(group) for group in checks["all"]) and any(
            group_loaded(group) for group in checks["one_of"]
        )
        if ok:
            print(f"{model}: ok")
            continue
        exit_code = 1
        required = ["+".join(group) for group in checks["all"] if not group_loaded(group)]
        variants = ["+".join(group) for group in checks["one_of"]]
        message = []
        if required:
            message.append("missing required: " + ", ".join(required))
        if variants and not any(group_loaded(group) for group in checks["one_of"]):
            message.append("one of: " + " or ".join(variants))
        print(f"{model}: {'; '.join(message)}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
