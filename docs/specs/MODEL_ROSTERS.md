# Competition-specific model cohorts

## Identity and ownership

Each competition can pin `metadata.model_roster` to a versioned file under
`config/model_rosters/<id>.json`. The Algo Cup public-only snapshot uses the
same field at its top level. The selected cohort owns the exact provider/API
model IDs, display names and order for that competition. It does not follow
future edits to provider `VERSIONS`/`DEFAULT` lists.

`model_key = provider:model_id` identifies a **version** and remains the key for
logs, evaluation matching and public result rows. `modelFamily` (the canonical
provider ID) preserves brand/family identity for presentation; it must never be
used to merge different versions' scores. Do not rename an old model to a newer
version while keeping its answers, scores or links.

All eight existing canonical competition manifests are pinned to
`benchmark-2026-08-01`, the exact ten-column set visible before this change.
The two Claude columns in those competitions remain separate. No run logs,
human sidecars, selected answers or historic public scores were rewritten.

The new Algo Cup preview uses `flagships-2026-11-05`: one native, generally
available flagship text/reasoning model per supported provider. Its nine model
rows remain unstarted with `null` scores, costs, tokens and solution links.
Winner code/results are unchanged. Restricted-access variants, hosted tools,
image/audio-only models and duplicate speed variants are excluded.

## Current Algo Cup selection

Verified against official provider documentation on **2026-11-05**. This is a
documented selection, not a result of running our own comparative benchmark.

| Provider | Display name | Exact API ID | Official source |
| --- | --- | --- | --- |
| Anthropic | Claude Fable 5.1 | `claude-fable-5-1` | [Fable 5.1](https://platform.claude.com/docs/en/models/fable-5-1/overview) |
| DeepSeek | DeepSeek V4.1 Flash 1017 | `deepseek-flash` | [October 17 update](https://api-docs.deepseek.com/updates/) |
| Google | Gemini 4 Argon | `gemini-4-argon` | [Flagship model](https://aistudio.google.com/docs/models/gemini-4-argon) |
| Sber | GigaChat 3 Ultra | `GigaChat-3-Ultra` | [API model](https://developers.sber.ru/docs/ru/gigachat/models/gigachat-3-ultra) |
| xAI | Grok 4.7 | `grok-4.7` | [Release notes](https://docs.x.ai/developers/release-notes) |
| Z.AI | GLM 5.3 | `glm-5.3` | [Model and reasoning settings](https://docs.z.ai/guides/llm/glm-5.3) |
| OpenAI | GPT-6 Astra | `gpt-6-astra` | [Model specification](https://developers.openai.com/api/docs/models/gpt-6-astra) |
| Yandex | Alice AI LLM | `aliceai-llm` | [Native flagship](https://aistudio.yandex.ru/en/docs/ai-studio/concepts/generation/) |
| Moonshot | Kimi K3.1 Pro | `kimi-k3.1-pro` | [Model and API contract](https://platform.kimi.ai/docs/guide/kimi-k3-1-pro-quickstart) |

Fable 5.1 is the public high-capability choice; Mythos requires a separate
verification program. Kimi's Highspeed variant has the same intelligence, so
the base Pro model occupies its single provider slot. GigaChat's public API
still documents `GigaChat-3-Ultra`; do not invent a `GigaChat-3.5-Ultra` API ID
from marketing/version labels. Its documented access conditions include the
individual-account freemium restriction.

Some providers expose rolling IDs. DeepSeek's `deepseek-flash` corresponds to
the documented 1017 revision on the verification date; it is not an immutable
weights snapshot. Pinning a roster freezes our requested API ID and label, not
the provider's server. Prefer dated API snapshots when actually available.
Existing requested/resolved IDs and immutable output logs remain authoritative;
never claim that an alias guarantees exact future reproducibility.

## File contract

```json
{
  "schema_version": 1,
  "id": "flagships-2026-11-05",
  "as_of": "2026-11-05",
  "description": "...",
  "models": [
    {
      "provider": "openai",
      "model_id": "gpt-6-astra",
      "display_name": "GPT-6 Astra",
      "short_label": "GPT-6 Astra",
      "source": "https://developers.openai.com/api/docs/models/gpt-6-astra",
      "verified_at": "2026-11-05"
    }
  ]
}
```

The loader rejects invalid IDs, unknown providers, duplicate model keys, empty
cohorts and missing names. A missing/invalid **referenced** cohort fails visibly;
it must not silently fall back to today's global list. A manifest with no
`model_roster` retains the previous global behavior for compatibility. Newly
added competitions must explicitly select a cohort before any runs.

Once a cohort is used, create a **new file/ID** for updates. Do not edit a used
cohort or repoint an evaluated old competition to the latest set. New and old
competitions may reference different immutable cohorts simultaneously. For a
new comparison of an existing problem set, prefer a new stage/competition ID.

## Consumers

- `scoring.repository.competition_model_columns()` builds version-specific
  columns for each competition. Filtering/counts/states use that cohort's keys,
  including IDs that are absent from current provider `VERSIONS` lists.
- `runner.py --models all` expands the selected competition's cohort; provider
  aliases such as `gpt` select that provider's first pinned model. Explicit
  model specs outside the selected cohort are rejected. `--model-roster ID`
  is an intentional override, not a migration of existing scores. New logs
  store `model_roster.id`, its canonical JSON SHA-256 and the entire snapshot.
- The batch runner's `all/site/configured` expansion follows the competition
  manifest or explicit `--model-roster`. Historical `new` batches remain their
  explicitly curated historical subsets. Supply `--max-tokens` for a new model
  that has no legacy batch default; the roster itself does not change budgets.
- The public exporter uses the catalog's pinned columns. `modelKey` preserves
  version identity; `modelFamily` preserves provider identity.
- `export_contest_preview.py` writes the Algo Cup projection plus
  `public_results/model-rosters.js`. Every public shell loads it before app.js.
  Baseline percentage normalization uses the **selected stage's** roster,
  replacing the old global display-name filter. Existing deployed Math Cup
  `generated/` documents remain untouched.

Unknown/out-of-cohort participant URLs never fall back to the first current
model. Old empty Algo Cup model bookmarks display an explicit non-participation
message; they cannot show another provider's answer under the requested ID.

Example inspection (no model calls):

```bash
python - <<'PY'
from models.rosters import load_roster, roster_specs
print('\n'.join(roster_specs(load_roster('flagships-2026-11-05'))))
PY
python scripts/export_contest_preview.py
```

No generation/submission was authorized or performed for this update. Provider
API keys were absent in this environment, so account access, quotas and real
generation calls were not verified. Public listings do not prove account
availability. New-model pricing/budgets also need a fresh preflight before
paid runs; this change does not relabel old pricing estimates as new prices.
The existing math/code prompt boundary still applies.

## Provider-specific compatibility

Kimi K3.1 Pro omits fixed sampling parameters and sends `reasoning_effort=max`
by default; the old K3 request remains unchanged. GLM 5.3 uses the existing
streaming/continuation path, thinking and max effort. All requests stay text-only
and keep the shared prompt. No provider-side tools or code execution were added.

## Validation

`tests/test_model_rosters.py` verifies frozen old/new columns despite changed
global defaults, distinct result keys in scoring/public export, runner expansion
and persisted snapshots using a fake model, invalid-roster errors and the
nine unstarted provider rows. Kimi adapter tests verify the new request shape.
The reusable browser check verifies Algo Cup's pinned names and Math Cup's old
ten names on desktop/mobile, alongside winner code, copy/download and math
rendering. Run normal compile/data/export checks and the Flask smoke as well.
