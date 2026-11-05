# Kimi / Moonshot AI

Current direct-adapter defaults match the nine-model `flagships-2026-11-05`
cohort. Historical competitions select their own pinned model IDs, regardless
of global defaults. All constructors accept request-scoped `system_prompt`;
runner selects a separate C++23/Python 3.13 prompt in explicit code mode. Only
the statement is sent; official solutions are optional. No tools or provider
code execution are enabled. See [model contracts](../../docs/specs/MODEL_ADAPTERS.md).

Competition rosters override the current direct-adapter default. The
November Algo Cup roster pins `kimi-k3.1-pro`: it omits fixed sampling
parameters (including temperature) and sends `reasoning_effort=max` by default,
per the official K3.1 API contract. Historical K3 requests remain unchanged.
See [MODEL_ROSTERS.md](../../docs/specs/MODEL_ROSTERS.md) for exact cohorts,
source documentation and the unverified account-access preflight.

The current text-only flagship is `kimi-k3.1-pro`. Put only `KIMI_API_KEY=...` in
`models/kimi/secrets/.env`. The adapter uses Moonshot's OpenAI-compatible
`https://api.moonshot.ai/v1/chat/completions` endpoint with the shared system
prompt, `max_completion_tokens=256000`, and `reasoning_effort=max`, omitting fixed sampling parameters. Legacy K3
continues to send temperature `1`. It sends no tools, search, code execution, files or
images. The API response's input, output, and reasoning-token counters are
persisted, with cost calculated from each exact model's list pricing.

Historical K3 final batch (intentionally retains the original model):

```bash
python scripts/run_kimi_math_cup_2026_final.py --yes
```
