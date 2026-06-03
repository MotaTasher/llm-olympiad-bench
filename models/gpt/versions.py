# models/gpt/versions.py
# Source:
#   https://developers.openai.com/api/docs/models
#   https://developers.openai.com/api/docs/models/all
#   https://developers.openai.com/api/docs/deprecations
#   https://developers.openai.com/api/reference/resources/models/methods/list
# Updated: 2026-06-03
#
# Scope:
#   Text-generation / chat-capable OpenAI API model IDs for Olympiad Scorer.
#   Image, audio, video, embeddings, moderation, realtime, and open-weight-only
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
    # Latest / frontier chat-completions-compatible models
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.4-nano",

    # Previous current GPT-5 family
    "gpt-5.3-codex",
    "gpt-5.2",
    "gpt-5.1",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",

    # Reasoning / older current families
    "o3-pro",
    "o3",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o-mini",

    # Mutable ChatGPT-style alias; API-callable, but not ideal as a stable default
    "chat-latest",
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

LEGACY_VERSIONS = [
    # Deprecated; scheduled for shutdown on 2026-08-10
    "gpt-5.3-chat-latest",
    "gpt-5.2-chat-latest",

    # Deprecated; scheduled for shutdown on 2026-07-23
    "gpt-5.2-codex",
    "gpt-5.1-chat-latest",
    "gpt-5.1-codex-max",
    "gpt-5.1-codex",
    "gpt-5.1-codex-mini",
    "gpt-5-chat-latest",
    "gpt-5-codex",
    "o3-deep-research",
    "o4-mini-deep-research",
    "gpt-4o-search-preview",
    "gpt-4o-mini-search-preview",

    # Deprecated; scheduled for shutdown on 2026-10-23
    "gpt-4.1-nano",
    "o4-mini",
    "o3-mini",
    "o1-pro",
    "o1",
    "o1-mini",
    "o1-preview",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",

    # Older legacy/base models; keep only if your adapter still supports them
    "gpt-3.5-turbo",
    "davinci-002",
    "babbage-002",

    # Deprecated ChatGPT/Codex aliases listed in the official catalog
    "chatgpt-4o-latest",
    "codex-mini-latest",
    "gpt-4.5-preview",
    "gpt-4-turbo-preview",
]

DEFAULT = VERSIONS[0]
