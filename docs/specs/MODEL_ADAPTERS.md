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

Adapters should fill provider-specific fields when the API exposes them, but must not invent missing metrics. If reasoning/cache usage or time-to-first-token is not returned or measured, leave it `null`/absent. Provider token-detail containers such as `output_tokens_details`, `completion_tokens_details`, `input_tokens_details`, Gemini Interactions `total_input_tokens`/`total_output_tokens`/`total_thought_tokens`/`total_cached_tokens`, Yandex `completionTokensDetails` and their `reasoningTokens`/`reasoning_tokens` counts are safe telemetry, not credentials. `SolveResult.to_log_dict()` preserves legacy fields while adding normalized telemetry and redacting unsafe data.

`max_tokens` is the runner-wide output/completion-token ceiling. Adapters map it
to the provider's text completion field (`max_completion_tokens`, `max_tokens`,
`maxTokens`, etc.) and include it in the safe request snapshot. When it is
`None`, provider-specific env settings remain the fallback.

## Failure behavior

`solve()` must catch provider, credential, parsing and network exceptions and return `error_result(...)`. It must not abort the outer runner.
If a provider returns a successful HTTP/API response but no visible answer text,
the adapter must return a `SolveResult` with `error` populated. Reasoning-only
or length-limited responses are not successful olympiad solutions.

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
provider, using explicit specs such as `openai:gpt-5.6-sol`. If `--models` is
omitted, runner reads `RUNNER_MODELS` from `config/models.env`; the committed
default is `RUNNER_MODELS=all`, so CLI runs match the scoring UI configured
columns. Individual model specs may be mixed with aliases, for example
`--models gpt,anthropic:claude-opus-5`.
`runner.py --max-tokens N` overrides the benchmark token budget for every
selected adapter in that run. The committed benchmark default is a common
256,000-token total output budget. Provider requests use that value whenever
their API permits it and record the safe request snapshot. A provider-specific
parameter constraint is documented next to the adapter rather than silently
lowering the common runner budget.
The OpenAI adapter maps this value to a total Responses API output budget. If
the total exceeds the configured per-request cap for the model, the adapter
continues with additional Responses requests linked by `previous_response_id`
until it receives non-empty visible output or exhausts the budget. This is still
text-only and does not add tools, browsing or provider-side execution.
The Grok adapter uses xAI's Responses API with the same total-budget behavior,
a 256,000-token per-request default and `previous_response_id` continuation.
The GLM adapter uses a 128,000-token per-request default; when a request has no
visible answer but returns `reasoning_content`, it appends that content
unmodified and continues with `clear_thinking=false`. The per-request defaults
may be adjusted with `XAI_MAX_OUTPUT_TOKENS_PER_REQUEST` and
`ZAI_MAX_TOKENS_PER_REQUEST` without changing the total runner budget.
GLM requests use a 7,200-second default HTTP timeout because 128K thinking
requests can exceed one hour; shorter retry steps may lower the per-request
token limit without discarding the total budget.
GLM 5.2 uses streaming chat completions and reconstructs the complete
`reasoning_content`, visible `content`, usage and finish reason from deltas. This
prevents a long first request from being lost while a non-streaming response is
buffered until the HTTP timeout; continuation still receives the exact joined
reasoning text.
GLM and Gemini must also continue responses that contain visible text but carry
a length-limited or incomplete finish reason. They retain visible fragments in
order and must not classify a still-incomplete response as successful after the
total continuation budget is exhausted.
OpenAI long Responses requests use `OPENAI_TIMEOUT_SECONDS` for the per-request
HTTP timeout, defaulting to 7200 seconds so 128K reasoning/output calls are not
cut off by the SDK's shorter default timeout. `OPENAI_MAX_RETRIES` may override
the SDK retry count when operators want to avoid or allow replaying long calls.
The Anthropic adapter treats `runner.py --max-tokens` as a total Claude output
budget. Each Messages request is capped by the provider/model maximum
(`claude-fable-5` and `claude-opus-5`: 128,000). Both active Claude models use
current Anthropic adaptive thinking:
`thinking: {"type": "adaptive", "display": "summarized"}` plus
`output_config.effort` (`max` in the committed benchmark runtime config).
Manual `budget_tokens` is only used for
models that still accept `thinking: {"type": "enabled"}`; the adapter clamps
that budget so each request keeps a visible-answer token reserve. If the total
budget is larger and a step returns no visible text, the adapter continues with
another Messages request by passing the previous assistant `content` blocks
unchanged and then a text-only `Continue.` user message. This preserves
Anthropic signed `thinking`/`redacted_thinking` blocks when they are returned,
without converting them to prompt text and without adding tools, search or code
execution. The adapter uses the non-streaming Messages API up to `max_tokens =
21333`, matching the Anthropic Python SDK's documented long-request threshold;
larger per-request steps automatically use Messages streaming and collect the
final message before returning `SolveResult`. When Anthropic returns
`output_tokens_details.reasoning_tokens`, the adapter stores it in
`usage.reasoning_tokens`; those tokens are billed as output tokens, so
`cost.reasoning` is a subcomponent of the already total-priced output cost.
Claude Fable 5 can return a refusal as HTTP 200; `stop_reason=refusal` is stored
as `SolveResult.error` and is not treated as a successful benchmark answer.

Current active set:

| Provider | Active model |
| --- | --- |
| OpenAI | `gpt-5.6-sol` |
| Anthropic | `claude-fable-5`, `claude-opus-5` |
| DeepSeek | `deepseek-v4-pro` |
| Gemini | `gemini-3.1-pro-preview` |
| GigaChat | `GigaChat-3-Ultra` |
| Grok | `grok-4.5` |
| GLM | `glm-5.2` |
| Yandex AI Studio | `aliceai-llm` |
| Moonshot AI | `kimi-k3` |

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
| `gemini`, `google` | `models.gemini.GeminiModel` |
| `gigachat`, `sber` | `models.gigachat.GigaChatModel` |
| `grok`, `xai` | `models.grok.GrokModel` |
| `glm`, `zai`, `zhipu` | `models.glm.GLMModel` |
| `yandex`, `yandexgpt` | `models.yandexgpt.YandexGPTModel` |
| `alice` | `models.yandexgpt.AliceModel` |
| `kimi`, `moonshot` | `models.kimi.KimiModel` |

Add aliases only in `runner.MODEL_CLASSES`, and update this table plus README examples.

## Current provider notes

- Gemini uses the official `google-genai` package and the Gemini Developer API.
  `gemini-3.1-pro-preview` is the active Google Pro reasoning model. The supported
  `gemini-3.5-flash` ID is legacy-only and does not create a benchmark column.
  Thinking is configured by provider thinking level
  (`GEMINI_THINKING_LEVEL=high` by default), not by inventing a token-budget
  conversion. `runner.py --max-tokens` is a total Gemini output/thinking budget:
  the adapter caps each Interactions API request at 65,536 output tokens and
  continues with `previous_interaction_id` when the total budget is larger. This
  preserves Gemini server-side conversation history and thought signatures
  without adding tools, search or code execution. Interactions API usage is
  normalized from `total_input_tokens`, `total_output_tokens`,
  `total_thought_tokens`, `total_cached_tokens` and `total_tokens`. Gemini
  Interactions reports visible output and thought output separately, so Gemini
  `cost.output` is visible output, `cost.reasoning` is thought output and
  `cost.total` includes both.
- Legacy Google logs that contain only `usage.total_tokens` recover an estimated
  cost during `normalize_legacy_result()`: input is estimated from the persisted
  text request and the remainder is priced as output/thinking. The source is
  marked `models/pricing.py:total-token-fallback`; the immutable log is not
  rewritten.
- GigaChat uses the official Python SDK with a 7,200-second request timeout and
  at most three SDK retries for transient HTTP failures. This avoids treating
  the SDK's 30-second default timeout as a completed model answer; all requests
  remain text-only.
- Kimi uses Moonshot's OpenAI-compatible Chat Completions endpoint with
  `kimi-k3`, the provider's current flagship available to this account. Its
  request contains only the shared system/user text messages,
  `max_completion_tokens=256000`, `temperature=1`, and `stream=false`; it
  deliberately omits `tools`, search, files, images, code execution, and
  function calls. K3 is the one active API model that accepts only temperature
  `1`. Usage is read from the returned `usage` object; K3 list-price estimates
  are stored separately from provider token counters.
- Grok uses xAI's hosted Responses endpoint under `https://api.x.ai/v1`.
  Stateful continuation preserves reasoning through `previous_response_id`.
  `grok-4.5` is the general-purpose flagship and receives
  `XAI_REASONING_EFFORT=high` by default. The legacy `grok-build-0.1` is a
  coding-specialized model but still receives only the text olympiad prompt;
  it must not get shell, repository tools, code execution or unsupported
  reasoning parameters. `grok-code-fast-1` canonicalizes to
  `grok-build-0.1`; Grok-1 is intentionally excluded because self-hosted
  inference is outside the project contract.
- GLM uses Z.AI's OpenAI-compatible endpoint
  `https://api.z.ai/api/paas/v4/`. `glm-5.2` is the paid flagship and gets
  thinking plus `reasoning_effort=max`; the legacy `glm-4.7-flash` remains
  callable explicitly and gets thinking when supported, but not the GLM-5.2-only
  reasoning effort field. Neither Flash ID is part of the active benchmark.
  Empty visible responses continue with exact preserved thinking rather than
  discarding the returned reasoning trace.

All provider-side tools remain disabled: no Google Search, X search, web
search, code execution, function calling, files, managed agents or remote MCP.

## Adding a provider

1. Create `models/<provider>/` with `__init__.py`, adapter, `versions.py`, README and `secrets/.gitkeep`.
2. Implement `BaseModel` and failure capture.
3. Use shared helpers from `models/common.py`.
4. Add aliases to `runner.py`.
5. Extend `scripts/check_secrets.py`.
6. Add dependency to `requirements.txt` only when needed.
7. Update root README and this spec.
8. Compile and run a credential-free error-path smoke test or a real API smoke test.
