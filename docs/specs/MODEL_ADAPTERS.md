# Model adapter contract

## Public interface

Every provider implements `BaseModel` from `models/base.py`:

```python
class BaseModel(abc.ABC):
    @property
    def model_id(self) -> str: ...

    def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult: ...
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

`max_tokens` is the runner-wide output/completion-token ceiling. Adapters map it
to the provider's text completion field (`max_completion_tokens`, `max_tokens`,
`maxTokens`, etc.) and include it in the safe request snapshot. When it is
`None`, provider-specific env settings remain the fallback.

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
Adapters may also accept explicit constructor settings from `runner.RunSettings`,
currently `reasoning_budget_tokens` and `max_final_tokens`. These settings are
request-scoped and take precedence over provider token-limit environment
variables for that model object. They must not add tools, web search, function
calling or provider-side code execution. Providers with no numeric reasoning
budget API leave that setting as best effort while still applying the visible
answer token cap when supported.

`VERSIONS` is the active benchmark set and should stay small. The scoring UI uses only `VERSIONS` for configured columns; `LEGACY_VERSIONS` may document retired IDs, but must not be used to seed the default matrix.

`runner.py --models all` expands to every active `VERSIONS` entry for every
provider, using explicit specs such as `openai:gpt-5.5`. If `--models` is
omitted, runner reads `RUNNER_MODELS` from `config/models.env`; the committed
default is `RUNNER_MODELS=all`, so CLI runs match the scoring UI configured
columns. Individual model specs may be mixed with aliases, for example
`--models gpt,anthropic:claude-opus-4-8`.
`runner.py --max-tokens N` overrides `RUNNER_MAX_TOKENS` (committed default:
`8000`) and provider-specific token env vars for all selected adapters in that
run.
`runner.py --pipeline draft-final` is provider-agnostic and uses the same
`BaseModel.solve()` method twice per selected model: once for a visible draft
and once for a finalizer prompt that receives only that draft. This does not add
tools, browsing or provider-side execution.
The Anthropic adapter uses the non-streaming Messages API up to `max_tokens =
21333`, matching the Anthropic Python SDK's documented long-request threshold.
For larger Claude requests it automatically switches to Messages streaming and
collects the final message before returning `SolveResult`; this is still a
text-only request and does not change API pricing.

Current active set:

| Provider | Active model |
| --- | --- |
| OpenAI | `gpt-5.5`, `gpt-5.4-mini` |
| Anthropic | `claude-opus-4-8`, `claude-haiku-4-5-20251001` |
| DeepSeek | `deepseek-v4-pro`, `deepseek-v4-flash` |
| GigaChat | `GigaChat-2-Max`, `GigaChat-2` |
| YandexGPT | `yandexgpt-5.1`, `yandexgpt-5-lite` |

Retired IDs may be listed in provider `LEGACY_VERSIONS` for operator context,
but they are not active benchmark models and must not create scoring UI columns
from historical logs. Equivalent aliases for the same active model must be
explicit; for example `yandexgpt-5.1/latest` is canonicalized to
`yandexgpt-5.1`, while unrelated similar names are not merged.

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
