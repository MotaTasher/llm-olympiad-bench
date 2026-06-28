# Model adapter contract

## Public interface

Every provider implements `BaseModel` from `models/base.py`:

```python
class BaseModel(abc.ABC):
    @property
    def model_id(self) -> str: ...

    def solve(self, problem: str) -> SolveResult: ...
```

`SolveResult` fields are:

- `model`;
- `answer`;
- `prompt_tokens`;
- `completion_tokens`;
- `cost_usd`;
- `latency_ms`;
- `raw_response`;
- optional `error`.

`SolveResult` also accepts optional telemetry fields used by schema v2 logs:

- `provider`;
- `requested_model_id` and `resolved_model_id`;
- safe `request` snapshot;
- structured `usage`, `timing`, `cost`;
- `finish_reason`, `provider_request_id`, `response_id`, `provider_timestamp`;
- structured `error_info`.

Adapters should fill provider-specific fields when the API exposes them, but must not invent missing metrics. If reasoning/cache usage or time-to-first-token is not returned or measured, leave it `null`/absent. `SolveResult.to_log_dict()` preserves legacy fields while adding normalized telemetry and redacting unsafe data.

## Failure behavior

`solve()` must catch provider, credential, parsing and network exceptions and return `error_result(...)`. It must not abort the outer runner.

`raw_response` must be JSON-serializable and redacted. Use `safe_dict()` for SDK objects. Request snapshots must not include API keys, Authorization headers, cookies, credentials, full secret `.env` contents, full environment dumps, hostnames or user/home-directory identifiers.

## Text-only policy

All providers receive only system/user text. These request keys are prohibited by `ensure_text_only_request()`:

```text
tool_choice
tools
function_call
functions
web_search_options
```

Do not bypass the guard. Adding any tool/search capability is a project-wide experimental-design change, not an adapter tweak.

The current adapters still use text-only system/user messages. Telemetry logging must not add tools, web search, function calling or provider-side code execution.

## Shared system prompt

`models/common.py::SYSTEM_PROMPT` requires rigorous olympiad reasoning and explicitly forbids tools, search, code and calculators. Changes affect every provider and comparability across runs.

## Model selection

Each adapter imports:

```python
from .versions import DEFAULT as DEFAULT_VERSION
```

Typical resolution:

```python
self._model = model or env("PROVIDER_MODEL", DEFAULT_VERSION)
```

Default identifiers belong in `versions.py`. Temporary overrides may live in `config/models.env` or inherited shell variables only when runner is invoked with `--allow-env-model-overrides`.

## Current aliases

| Alias | Class |
| --- | --- |
| `gpt`, `openai` | `models.gpt.GPTModel` |
| `claude`, `anthropic` | `models.claude.ClaudeModel` |
| `deepseek`, `ds` | `models.deepseek.DeepSeekModel` |
| `gigachat`, `sber` | `models.gigachat.GigaChatModel` |
| `yandex`, `yandexgpt` | `models.yandexgpt.YandexGPTModel` |
| `alice` | `models.yandexgpt.AliceModel` |

Add aliases only in `runner.MODEL_CLASSES`, and update this table plus README examples.

## Adding a provider

1. Create `models/<provider>/` with `__init__.py`, adapter, `versions.py`, README and `secrets/.gitkeep`.
2. Implement `BaseModel` and failure capture.
3. Use shared helpers from `models/common.py`.
4. Add aliases to `runner.py`.
5. Extend `scripts/check_secrets.py`.
6. Add dependency to `requirements.txt` only when needed.
7. Update root README and this spec.
8. Compile and run a credential-free error-path smoke test or a real API smoke test.
