# Gemini adapter

Runs Google Gemini through the official `google-genai` package in text-only mode.

Active models:

- `gemini-3.1-pro-preview` — preview Pro model, default high thinking level.
- `gemini-3.5-flash` — Flash model that may have Free Tier/API Studio allowance, but runner telemetry uses paid-list estimates.

Secrets go only in:

```text
models/gemini/secrets/.env
```

```env
GEMINI_API_KEY=...
```

Public runtime settings belong in `config/models.env`:

```env
GEMINI_THINKING_LEVEL=high
GEMINI_TEMPERATURE=0.2
GEMINI_MAX_OUTPUT_TOKENS=8192
GEMINI_TIMEOUT_SECONDS=3600
```

Credential-free smoke:

```bash
python - <<'PY'
from models.gemini import GeminiModel
for model_id in ["gemini-3.1-pro-preview", "gemini-3.5-flash"]:
    result = GeminiModel(model_id).solve("Докажите, что 1 = 1.", max_tokens=32)
    assert result.error
    print(model_id, "error path ok")
PY
```

The adapter sends the shared `SYSTEM_PROMPT`, a single text prompt and no provider tools, search, files, images, managed agents or code execution. The shared `ensure_text_only_request()` guard validates the request snapshot before the API call.
