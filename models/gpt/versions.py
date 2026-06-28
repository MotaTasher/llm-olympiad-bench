# models/gpt/versions.py
# Source:
#   https://developers.openai.com/api/docs/models
#   https://developers.openai.com/api/docs/models/all
#   https://developers.openai.com/api/docs/deprecations
#   https://developers.openai.com/api/reference/resources/models/methods/list
# Updated: 2026-06-29
#
# Scope:
#   Active OpenAI API model IDs for Olympiad Scorer.
#   Keep only the strongest paid model and the strongest budget model that
#   the current Chat Completions adapter can call. Image, audio, video,
#   embeddings, moderation, realtime, search, and open-weight-only models are
#   intentionally excluded.
#
# Programmatic check:
#   OpenAI has an authenticated public list-models endpoint.
#
#   curl https://api.openai.com/v1/models \
#     -H "Authorization: Bearer $OPENAI_API_KEY"
#
#   python - <<'PY'
#   from openai import OpenAI
#   client = OpenAI()
#   for m in sorted(client.models.list().data, key=lambda x: x.id):
#       print(m.id)
#   PY
#
# Notes:
#   - /v1/models is the source of truth for what YOUR key/project can call.
#   - Availability and rate limits depend on org/project usage tier.
#   - Some "pro" models can be slower/more expensive and may have feature
#     restrictions such as no streaming.
#   - Dated snapshots are not listed here; use /v1/models if you want pinned
#     snapshot IDs instead of stable aliases.

VERSIONS = [
    # Strongest paid chat-completions-compatible model.
    "gpt-5.5",

    # OpenAI API does not expose a separate free model ID for this adapter.
    # Use the strongest current mini/budget model as the low-cost column.
    "gpt-5.4-mini",
]

NON_CHAT_COMPLETIONS_VERSIONS = [
    # These are API model IDs, but the current adapter uses
    # /v1/chat/completions and they fail there. Use a Responses API adapter
    # before selecting them.
    "gpt-5.5-pro",
    "gpt-5.4-pro",
    "gpt-5.2-pro",
    "gpt-5-pro",
]

LEGACY_VERSIONS = []

DEFAULT = VERSIONS[0]
