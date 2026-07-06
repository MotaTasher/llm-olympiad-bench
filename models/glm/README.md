# GLM adapter

Runs Z.AI GLM models through the OpenAI-compatible endpoint:

```text
https://api.z.ai/api/paas/v4/
```

Active models:

- `glm-5.2` — flagship paid model; thinking is enabled and `reasoning_effort=max` is sent.
- `glm-4.7-flash` — official free hosted lightweight model; thinking is enabled when supported, but `reasoning_effort` is not sent.

`glm-4.7-flashx` is not part of the active benchmark and does not receive the free pricing rule.

## 1. How to get an API key

1. Open the Z.AI API platform: [z.ai/model-api](https://z.ai/model-api).
2. Register or log in to the Z.AI Open Platform.
3. Open API Keys management and create a new key.
4. Copy the key immediately.
5. Check account balance, model access and rate limits before large benchmark runs.

Z.AI's HTTP API guide documents the same flow:
[docs.z.ai/guides/develop/http/introduction](https://docs.z.ai/guides/develop/http/introduction).

## 2. How to store the key

Secrets go only in:

```text
models/glm/secrets/.env
```

```env
ZAI_API_KEY=...
```

Do not commit this file and do not put model/runtime settings in the secrets file.

## 3. Runtime settings

Public runtime settings belong in `config/models.env`:

```env
ZAI_BASE_URL=https://api.z.ai/api/paas/v4/
ZAI_THINKING=enabled
ZAI_REASONING_EFFORT=max
ZAI_MAX_TOKENS=8192
ZAI_TIMEOUT_SECONDS=3600
ZAI_MAX_RETRIES=0
```

Credential-free smoke:

```bash
python - <<'PY'
from models.glm import GLMModel
for model_id in ["glm-5.2", "glm-4.7-flash"]:
    result = GLMModel(model_id).solve("Докажите, что 1 = 1.", max_tokens=32)
    assert result.error
    print(model_id, "error path ok")
PY
```

The adapter sends the shared `SYSTEM_PROMPT`, a single text prompt and no provider tools, search, files, managed agents or code execution. Provider `reasoning_content` may be retained in redacted raw telemetry but is never included in the visible answer.
