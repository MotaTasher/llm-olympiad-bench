# Kimi / Moonshot AI

The active text-only flagship is `kimi-k2.5`. Put only `KIMI_API_KEY=...` in
`models/kimi/secrets/.env`. The adapter uses Moonshot's OpenAI-compatible
`https://api.moonshot.ai/v1/chat/completions` endpoint with the shared system
prompt, temperature 0.1 and a 256,000-token requested output budget. It sends
no tools, search, code execution, files or images.

Run only missing Kimi pairs for the final:

```bash
python scripts/run_kimi_math_cup_2026_final.py --yes
```
