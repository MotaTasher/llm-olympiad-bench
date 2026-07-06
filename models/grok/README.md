# Grok adapter

Runs xAI Grok models through the official hosted OpenAI-compatible endpoint:

```text
https://api.x.ai/v1
```

Active models:

- `grok-4.3` — general-purpose reasoning model; default `XAI_REASONING_EFFORT=high`.
- `grok-build-0.1` — coding-specialized baseline, still used only as a text solver. No shell, repository tools or code execution are attached.

`grok-code-fast-1` is treated only as a legacy alias and canonicalizes to `grok-build-0.1`; it is not a separate benchmark column.

Secrets go only in:

```text
models/grok/secrets/.env
```

```env
XAI_API_KEY=...
```

Public runtime settings belong in `config/models.env`:

```env
XAI_BASE_URL=https://api.x.ai/v1
XAI_REASONING_EFFORT=high
XAI_MAX_OUTPUT_TOKENS=8192
XAI_TIMEOUT_SECONDS=3600
XAI_MAX_RETRIES=0
```

Credential-free smoke:

```bash
python - <<'PY'
from models.grok import GrokModel
for model_id in ["grok-4.3", "grok-build-0.1"]:
    result = GrokModel(model_id).solve("Докажите, что 1 = 1.", max_tokens=32)
    assert result.error
    print(model_id, "error path ok")
PY
```

The adapter sends the shared `SYSTEM_PROMPT`, a single text prompt and no provider tools, search, files, managed agents or code execution. If xAI returns `cost_in_usd_ticks`, that provider-reported cost overrides the local pricing estimate.
