# DeepSeek

## Secrets

Create `models/deepseek/secrets/.env`:

```env
DEEPSEEK_API_KEY=...
```

Optional runtime settings go in `config/models.env`:

```env
# DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEMPERATURE=0.3
```

## Model IDs

See `models/deepseek/versions.py`.

Official list endpoint:

```bash
curl https://api.deepseek.com/models \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY"
```

## Text-only policy

The adapter uses DeepSeek's OpenAI-compatible Chat Completions API and does not pass `tools`.
