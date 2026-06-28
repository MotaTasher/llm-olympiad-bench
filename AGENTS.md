# Agent Guide

Этот документ описывает архитектуру и контракты проекта для агентов и разработчиков, которые меняют код.

Пользовательские инструкции по запуску лежат в [README.md](README.md).

## Назначение проекта

`Olympiad Scorer` сравнивает решения LLM на олимпиадных задачах:

1. Загружает задачу из `data/problems/`.
2. Запускает выбранные модели через адаптеры в `models/`.
3. Сохраняет результаты в `logs/<competition_id>/<problem_id>/<run_id>.json`.
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
│   ├── deepseek/
│   │   ├── __init__.py        # export DeepSeekModel
│   │   ├── deepseek.py        # DeepSeek adapter
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
    ├── competitions/
    │   └── local_examples/
    │       ├── competition.json
    │       └── problems/
    │           ├── example.json
    │           └── tug_tug_500.json
    ├── problems/
    │   └── example.json         # legacy/simple problem location
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

The adapter reads `DEFAULT` as its fallback version. To override for a specific run, set the env variable (e.g. `OPENAI_MODEL=gpt-4o-mini`) in `config/models.env`.

Stale `*_MODEL` values in inherited shell env, `.env`, and `models/*/secrets/.env` are ignored by `runner.load_env()` by default. Those files are credentials-only. Shell env model overrides are allowed only when `runner.py` is called with `--allow-env-model-overrides`.

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
deepseek, ds   -> models.deepseek.DeepSeekModel
gigachat, sber -> models.gigachat.GigaChatModel
yandex, yandexgpt -> models.yandexgpt.YandexGPTModel
alice          -> models.yandexgpt.AliceModel
```

## Runner Contract

CLI:

```bash
python runner.py \
  --problem data/problems/task1.json \
  --models gpt,claude,gigachat,yandexgpt,deepseek \
  --run-id my_run_01
```

`--run-id` is a human-readable run name suffix. The final generated `run_id`
and log filename use:

```text
YYYY_MM_DD_HH_MM_SS_<name>
```

If `--run-id` is omitted, `<name>` is taken from problem `title`, then `id`,
then the problem filename stem.

Behavior:

1. Load env from `.env`.
2. Load model-local env files from `models/*/secrets/.env` and `models/*/secrets/*.env`.
3. Load public runtime config from `config/models.env`; overrides stale settings from secret files.
4. Load problem text:
   - JSON: field `text`;
   - Markdown/other text: full file contents.
   - canonical competition paths:
     `data/competitions/<competition_id>/problems/<problem_id>.json`;
   - if a problem is under `data/competitions/<competition_id>/problems/`,
     read `data/competitions/<competition_id>/competition.json` as competition metadata
     unless CLI or problem metadata overrides it.
5. Instantiate adapters from aliases.
6. Call `solve()` sequentially.
7. Write `logs/<competition_id>/<problem_id>/<run_id>.json`.
8. Print table: model, tokens, cost, latency, status, short error.

## Log Format

```json
{
  "run_id": "2026_06_02_15_30_00_task1",
  "timestamp": "2026-06-02T15:30:00Z",
  "git_hash": "17ea460",
  "competition_id": "school_2026",
  "competition_title": "Школьная олимпиада 2026",
  "problem_id": "task1",
  "problem_title": "Название задачи",
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

New logs are stored under:

```text
logs/<competition_id>/<problem_id>/<run_id>.json
```

Old root-level `logs/*.json` files are still supported by `scoring/app.py` and
shown under competition `legacy`.

## Problem Format

Canonical storage:

```text
data/competitions/<competition_id>/competition.json
data/competitions/<competition_id>/problems/<problem_id>.json
```

`competition.json`:

```json
{
  "id": "school_2026",
  "title": "Школьная олимпиада 2026",
  "description": "Optional human-readable note"
}
```

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

- `GET /`: list competitions;
- `GET /competition/<competition_id>`: list problems for a competition;
- `GET /competition/<competition_id>/problem/<problem_id>`: list runs for a problem;
- `GET /competition/<competition_id>/problem/<problem_id>/run/<run_id>`: review page;
- `GET /run/<run_id>`: legacy redirect to the structured review page;
- `POST /score`: update scoring sidecar fields in `data/results/<competition_id>/<problem_id>/<run_id>.json`.

Review UI requirements:

- show competitions first;
- inside a competition, show problems;
- inside a problem, show runs;
- show problem text;
- keep answers hidden behind click/expand before review;
- allow score 0-10, reviewer name, comment;
- show metrics after score exists.

Scoring storage:

```text
data/results/<competition_id>/<problem_id>/<run_id>.json
```

The sidecar file stores `evaluations`, keyed by result index from the run log's
`results[]`. Run logs remain the source of model answers; sidecars are the
source of manual scoring.

## Server Sync

Local model runs can be pushed to the scoring server with:

```bash
python scripts/sync_logs.py push
```

Scoring fields can be pulled back with:

```bash
python scripts/sync_logs.py pull
```

The remote is configured privately through:

```text
config/server.env
```

`config/server.env` is gitignored. Use `config/server.env.example` as the public
template. Override with `SCORER_REMOTE_LOGS` or `--remote`. Push uses
`rsync --ignore-existing` to avoid overwriting server-side scoring edits.

## Text-Only API Policy

All adapters should call provider APIs without tools.

| Provider | Policy |
| --- | --- |
| OpenAI GPT | Do not pass `tools`. |
| Anthropic Claude | Do not pass `tools`. |
| DeepSeek | Do not pass `tools`; use OpenAI-compatible Chat Completions. |
| GigaChat | Do not pass `tools`, `functions`, or `function_call`. |
| YandexGPT | Use basic completion endpoint; tools are not part of this API. |

Reasoning/runtime settings:

- OpenAI GPT can use `OPENAI_REASONING_EFFORT` and `OPENAI_MAX_COMPLETION_TOKENS`.
- Claude can use `ANTHROPIC_MAX_TOKENS`; `ANTHROPIC_THINKING_BUDGET_TOKENS`
  enables extended thinking and must be lower than `ANTHROPIC_MAX_TOKENS`.
- DeepSeek can use `DEEPSEEK_MAX_TOKENS`; for reasoning models this caps output
  including reasoning content where the provider API counts it that way.
- YandexGPT supports `completionOptions.reasoningOptions.mode`; use `YANDEX_REASONING_MODE=ENABLED_HIDDEN` for hidden reasoning or `DISABLED` to turn it off.
- GigaChat currently uses sampling/length controls (`GIGACHAT_TEMPERATURE`, `GIGACHAT_TOP_P`, `GIGACHAT_MAX_TOKENS`, `GIGACHAT_REPETITION_PENALTY`) plus the strongest available model. Do not add tools/functions.
- Providers generally support maximum reasoning/output budgets, not guaranteed
  minimum thinking budgets. Encourage more reasoning through effort settings,
  enough token budget, and the shared system prompt.

## Validation

Before committing code changes:

```bash
python -m compileall runner.py models scripts scoring
python scripts/check_secrets.py --models gpt,claude,gigachat,yandexgpt,deepseek
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
