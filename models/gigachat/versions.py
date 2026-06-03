# models/gigachat/versions.py
# Source:
# - https://developers.sber.ru/docs/ru/gigachat/models/main
# - https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/get-models
# - https://developers.sber.ru/docs/ru/gigachat/guides/preview-models
# - https://developers.sber.ru/docs/ru/gigachat/tariffs/individual-tariffs
# Updated: 2026-06-03

VERSIONS = [
    # Production chat/completions models
    "GigaChat-2-Max",
    "GigaChat-2-Pro",
    "GigaChat-2",

    # Early-access API models; keep below production models,
    # because behavior/availability can change.
    "GigaChat-2-Max-preview",
    "GigaChat-2-Pro-preview",
    "GigaChat-2-preview",
]

LEGACY_VERSIONS = [
    # First-generation IDs / aliases.
    # Official docs say requests to GigaChat, GigaChat-Pro and
    # GigaChat-Max are redirected to GigaChat-2, GigaChat-2-Pro
    # and GigaChat-2-Max respectively.
    "GigaChat-Max",
    "GigaChat-Pro",
    "GigaChat",

    # Legacy/old preview IDs shown by the official SDK /models example.
    "GigaChat-Max-preview",
    "GigaChat-Pro-preview",
    "GigaChat-Plus",
    "GigaChat-Plus-preview",
    "GigaChat-preview",
]

DEFAULT = VERSIONS[0]