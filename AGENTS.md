# Agent Guide

Этот документ описывает архитектуру и контракты проекта для агентов и разработчиков, которые меняют код.

Пользовательские инструкции по запуску лежат в [README.md](README.md).

## Назначение проекта

`Olympiad Scorer` сравнивает решения LLM на олимпиадных задачах:

1. Загружает задачу из `data/problems/`.
2. Запускает выбранные модели через адаптеры в `models/`.
3. Сохраняет результаты в `logs/<run_id>.json`.
4. Позволяет вручную оценить ответы через `scoring/app.py`.

Модели должны работать в режиме text-only: без инструментов, поиска, кода, function calling и внешних цепочек.

## Структура

```text
olympiad-scorer/
├── README.md                  # инструкция для людей
├── AGENTS.md                  # архитектура и контракты для агентов
├── .env.example
├── requirements.txt
├── runner.py                  # единый CLI-запуск
├── scripts/
│   └── check_secrets.py       # preflight без вывода секретов
├── notebooks/
│   └── test_gpt_runner.ipynb
├── models/
│   ├── __init__.py
│   ├── base.py                # BaseModel + SolveResult
│   ├── common.py              # env helpers, timing, serialization
│   ├── gpt/
│   │   ├── __init__.py        # export GPTModel
│   │   ├── gpt.py             # OpenAI GPT adapter
│   │   ├── versions.py        # список версий + DEFAULT
│   │   ├── secrets/.env       # gitignored credentials
│   │   └── README.md
│   ├── claude/
│   │   ├── __init__.py        # export ClaudeModel
│   │   ├── claude.py          # Anthropic Claude adapter
│   │   ├── versions.py
│   │   └── README.md
│   ├── gigachat/
│   │   ├── __init__.py        # export GigaChatModel
│   │   ├── gigachat.py        # Sber GigaChat adapter
│   │   ├── versions.py
│   │   ├── secrets/.env
│   │   └── README.md
│   └── yandexgpt/
│       ├── __init__.py        # export YandexGPTModel, AliceModel
│       ├── yandexgpt.py       # YandexGPT adapter
│       ├── versions.py
│       ├── secrets/.env
│       └── README.md
├── config/
│   └── models.env             # non-secret runtime settings (no model versions)
├── logs/
│   └── .gitkeep               # JSON logs are gitignored
├── scoring/
│   ├── app.py
│   └── templates/
│       ├── index.html
│       └── review.html
└── data/
    ├── problems/
    │   └── example.json
    └── results/
        └── .gitkeep
```

Secrets live in `models/*/secrets/.env` — these folders must stay gitignored and contain credentials only.

Public model/runtime configuration lives in:

```text
config/models.env
```

This file is committed and controls non-secret runtime settings (temperatures, token limits, exchange rates). It does **not** set model versions — those come from `versions.py`.

## Version Selection

Each model folder contains a `versions.py` file:

```python
VERSIONS = ["gpt-4o", "gpt-4o-mini", "o3", "o4-mini"]
DEFAULT = VERSIONS[0]
```

The adapter reads `DEFAULT` as its fallback version. To override for a specific run, set the env variable (e.g. `OPENAI_MODEL=gpt-4o-mini`) in `config/models.env` or in the shell before invoking `runner.py`.

Stale `*_MODEL` values in `.env` and `models/*/secrets/.env` are ignored by `runner.load_env()`. Those files are credentials-only.

When adding a new model version: add it to `VERSIONS` in the appropriate `versions.py`. To change the default: move the desired version to `VERSIONS[0]`.

## Base Interface

`models/base.py` defines the shared contract.

```python
from dataclasses import dataclass
from typing import Optional
import abc

@dataclass
class SolveResult:
    model: str
    answer: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    raw_response: dict
    error: Optional[str] = None

class BaseModel(abc.ABC):
    @property
    @abc.abstractmethod
    def model_id(self) -> str:
        ...

    @abc.abstractmethod
    def solve(self, problem: str) -> SolveResult:
        ...
```

Rules:

- Every adapter inherits `BaseModel`.
- `solve()` accepts the full problem text and returns `SolveResult`.
- `solve()` must not raise API/network/key exceptions to the caller.
- Failures are represented as `SolveResult(error="...")`.
- `raw_response` should be JSON-serializable and safe for debug logs.
- Do not pass tools/functions/code execution/search unless the project contract is explicitly changed.

## Adapter Expectations

Each adapter (`models/<provider>/<provider>.py`) should:

- read credentials from environment variables;
- rely on `runner.load_env()` to load `.env`, `models/*/secrets/.env`, and `config/models.env`;
- resolve default version from `from .versions import DEFAULT as DEFAULT_VERSION`;
- allow env-var override (e.g. `env("OPENAI_MODEL", DEFAULT_VERSION)`);
- calculate `cost_usd` where pricing is known;
- return token counts when provider response includes them;
- keep provider-specific response parsing inside the adapter.

Current aliases in `runner.py`:

```text
gpt, openai    -> models.gpt.GPTModel
claude, anthropic -> models.claude.ClaudeModel
gigachat, sber -> models.gigachat.GigaChatModel
yandex, yandexgpt -> models.yandexgpt.YandexGPTModel
alice          -> models.yandexgpt.AliceModel
```

## Runner Contract

CLI:

```bash
python runner.py \
  --problem data/problems/task1.json \
  --models gpt,claude,gigachat,yandexgpt \
  --run-id my_run_01
```

Behavior:

1. Load env from `.env`.
2. Load model-local env files from `models/*/secrets/.env` and `models/*/secrets/*.env`.
3. Load public runtime config from `config/models.env`; overrides stale settings from secret files.
4. Load problem text:
   - JSON: field `text`;
   - Markdown/other text: full file contents.
5. Instantiate adapters from aliases.
6. Call `solve()` sequentially.
7. Write `logs/<run_id>.json`.
8. Print table: model, tokens, cost, latency, status, short error.

## Log Format

```json
{
  "run_id": "20260602_153000",
  "timestamp": "2026-06-02T15:30:00Z",
  "git_hash": "17ea460",
  "problem_file": "data/problems/task1.json",
  "problem_text": "Условие задачи...",
  "problem": {},
  "results": [
    {
      "model": "gpt-4o",
      "answer": "Решение...",
      "prompt_tokens": 312,
      "completion_tokens": 850,
      "cost_usd": 0.0045,
      "latency_ms": 2340,
      "raw_response": {},
      "error": null,
      "score": null,
      "scored_by": null,
      "scored_at": null,
      "score_comment": null
    }
  ]
}
```

`git_hash` — короткий SHA HEAD на момент запуска; пустая строка если git недоступен.

Do not change this format without updating `runner.py`, `scoring/app.py`, templates, and this document.

## Problem Format

JSON:

```json
{
  "id": "task1",
  "title": "Название задачи",
  "source": "Олимпиада X, 2025",
  "text": "Полный текст условия...",
  "expected_answer": null
}
```

Markdown is accepted as raw problem text.

## Scoring App

`scoring/app.py` uses Flask.

Endpoints:

- `GET /`: list run logs from `logs/`;
- `GET /run/<run_id>`: review page;
- `POST /score`: update score fields in the JSON log.

Review UI requirements:

- show problem text;
- keep answers hidden behind click/expand before review;
- allow score 0-10, reviewer name, comment;
- show metrics after score exists.

## Text-Only API Policy

All adapters should call provider APIs without tools.

| Provider | Policy |
| --- | --- |
| OpenAI GPT | Do not pass `tools`. |
| Anthropic Claude | Do not pass `tools`. |
| GigaChat | Do not pass `tools`, `functions`, or `function_call`. |
| YandexGPT | Use basic completion endpoint; tools are not part of this API. |

## Validation

Before committing code changes:

```bash
python -m compileall runner.py models scripts scoring
python scripts/check_secrets.py --models gpt,gigachat,yandexgpt
python runner.py --problem data/problems/example.json --models gpt --run-id smoke_gpt
```

Provider calls may fail if secrets or accounts are unavailable. In that case, verify that the failure is captured in `SolveResult.error` and written to the log.

## Implementation Priorities

When extending the project:

1. Preserve `SolveResult` and log compatibility.
2. Keep secrets out of git.
3. Keep model versions in `models/<provider>/versions.py`, not in `config/models.env` or hardcoded in adapters.
4. Keep non-secret runtime settings (temperatures, limits) in `config/models.env`.
5. Prefer provider SDKs when stable and installed.
6. Keep new provider-specific logic inside its adapter.
7. Add README notes for humans only when behavior affects setup or operation.
8. Add AGENTS notes when behavior affects contracts, architecture, or future agent work.
