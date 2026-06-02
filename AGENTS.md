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
│   ├── gpt.py                 # OpenAI GPT
│   ├── claude.py              # Anthropic Claude
│   ├── gigachat.py            # Sber GigaChat
│   ├── yandexgpt.py           # YandexGPT
│   ├── alice.py               # alias to YandexGPT
│   ├── gpt/README.md
│   ├── claude/README.md
│   ├── gigachat/README.md
│   └── yandexgpt/README.md
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

Secrets live beside model-specific docs/code:

```text
models/*/secrets/.env
```

These folders must stay ignored by git.

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

Each adapter file should:

- read credentials from environment variables;
- rely on `runner.load_env()` to load `.env` and `models/*/secrets/.env`;
- calculate `cost_usd` where pricing is known;
- return token counts when provider response includes them;
- keep provider-specific response parsing inside the adapter.

Current aliases in `runner.py`:

```text
gpt, openai -> models.gpt.GPTModel
claude, anthropic -> models.claude.ClaudeModel
gigachat, sber -> models.gigachat.GigaChatModel
yandex, yandexgpt -> models.yandexgpt.YandexGPTModel
alice -> models.alice.AliceModel
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
3. Load problem text:
   - JSON: field `text`;
   - Markdown/other text: full file contents.
4. Instantiate adapters from aliases.
5. Call `solve()` sequentially.
6. Write `logs/<run_id>.json`.
7. Print table: model, tokens, cost, latency, status, short error.

## Log Format

```json
{
  "run_id": "20260602_153000",
  "problem_file": "data/problems/task1.json",
  "problem_text": "Условие задачи...",
  "problem": {},
  "timestamp": "2026-06-02T15:30:00Z",
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
3. Prefer provider SDKs when stable and installed.
4. Keep new provider-specific logic inside its adapter.
5. Add README notes for humans only when behavior affects setup or operation.
6. Add AGENTS notes when behavior affects contracts, architecture, or future agent work.
