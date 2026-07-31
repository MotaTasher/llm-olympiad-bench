# Gemini adapter

Runs Google Gemini through the official `google-genai` package in text-only mode.

Active models:

- `gemini-3.5-flash` — strongest current model for sustained frontier reasoning, default high thinking level.

`gemini-3.5-flash` remains explicitly callable as a legacy model, but it no
longer creates a default scoring or public-results column.

## 1. How to get an API key

1. Open [Google AI Studio](https://aistudio.google.com/app/apikey) with the Google account that should own billing and quota.
2. Open the API keys page and click **Create API key**.
3. Copy the generated Gemini API key immediately.
4. Check project billing, quotas and any spend controls before running large benchmarks.

Google's current Gemini API key guide is here:
[ai.google.dev/gemini-api/docs/api-key](https://ai.google.dev/gemini-api/docs/api-key).

## 2. How to store the key

Secrets go only in:

```text
models/gemini/secrets/.env
```

```env
GEMINI_API_KEY=...
```

Do not commit this file and do not put model/runtime settings in the secrets file.

## 3. Runtime settings

Public runtime settings belong in `config/models.env`:

```env
GEMINI_THINKING_LEVEL=high
GEMINI_TEMPERATURE=0.2
GEMINI_MAX_OUTPUT_TOKENS=8192
GEMINI_TIMEOUT_SECONDS=3600
```

`runner.py --max-tokens N` is treated as a total Gemini output/thinking budget.
Gemini's per-request output cap is 65,536 tokens, so the adapter splits larger
budgets into multiple Interactions API requests and links them with
`previous_interaction_id`. This preserves Gemini's server-side reasoning context
and thought signatures while keeping the request text-only. For example,
`--max-tokens 256000` can use up to four Gemini requests.
Responses whose finish reason is `incomplete`, `length` or a max-token variant
are continued even when they already contain visible text. Visible fragments
are retained in order, and a response still marked incomplete after exhausting
the total budget is logged as an error rather than a successful truncated
solution.
Usage telemetry is read from the Interactions API `usage` fields:
`total_input_tokens`, `total_output_tokens`, `total_thought_tokens`,
`total_cached_tokens` and `total_tokens`. Thinking tokens are billed as output
telemetry by the local benchmark estimator: `cost.output` is visible output,
`cost.reasoning` is thought output and `cost.total` includes both. A response
with no visible text is logged as an adapter error even when the provider HTTP
request succeeds.

The estimator uses Google API Standard rates. For legacy Gemini logs that
persisted only `usage.total_tokens`, normalization estimates input tokens from
the saved text request and treats the remaining total as output/thinking
tokens. The recovered `cost.total` is marked with the
`models/pricing.py:total-token-fallback` source and an explanatory note. This
keeps old immutable run logs unchanged and makes the estimate visibly distinct
from exact provider token counters.

Credential-free smoke:

```bash
python - <<'PY'
from models.gemini import GeminiModel
for model_id in ["gemini-3.5-flash", "gemini-3.1-pro-preview"]:
    result = GeminiModel(model_id).solve("Докажите, что 1 = 1.", max_tokens=32)
    assert result.error
    print(model_id, "error path ok")
PY
```

The adapter sends the shared `SYSTEM_PROMPT`, a single text prompt and no provider tools, search, files, images, managed agents or code execution. The shared `ensure_text_only_request()` guard validates the request snapshot before the API call.
