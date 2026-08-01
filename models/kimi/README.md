# Kimi / Moonshot AI

The active text-only flagship is `kimi-k3`. Put only `KIMI_API_KEY=...` in
`models/kimi/secrets/.env`. The adapter uses Moonshot's OpenAI-compatible
`https://api.moonshot.ai/v1/chat/completions` endpoint with the shared system
prompt, `max_completion_tokens=256000`, and temperature `1` (the only K3 value
accepted by the API). It sends no tools, search, code execution, files or
images. The API response's input, output, and reasoning-token counters are
persisted, with cost calculated from K3's official list pricing.

Run only missing Kimi pairs for the final:

```bash
python scripts/run_kimi_math_cup_2026_final.py --yes
```
