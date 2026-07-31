# models/gpt/versions.py
# Source:
#   https://developers.openai.com/api/docs/models
#   https://developers.openai.com/api/docs/models/all
#   https://developers.openai.com/api/docs/deprecations
#   https://developers.openai.com/api/reference/resources/models/methods/list
# Updated: 2026-07-31
#
# Scope:
#   Active OpenAI API model IDs for Olympiad Scorer.
#   Keep only the strongest paid model in the active benchmark. Image, audio,
#   video, embeddings, moderation, realtime, search, and open-weight-only
#   models are intentionally excluded.
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
    # Strongest paid reasoning model.
    "gpt-5.5",
]

LEGACY_VERSIONS = ["gpt-5.4-mini"]

DEFAULT = VERSIONS[0]
