# models/gigachat/versions.py
# Source:
# - https://developers.sber.ru/docs/ru/gigachat/models/main
# - https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/get-models
# - https://developers.sber.ru/docs/ru/gigachat/guides/preview-models
# - https://developers.sber.ru/docs/ru/gigachat/tariffs/individual-tariffs
# Updated: 2026-06-29

VERSIONS = [
    # Strongest paid production model.
    "GigaChat-2-Max",

    # Strongest basic/free-tier production model available through this adapter.
    "GigaChat-2",
]

LEGACY_VERSIONS = []

DEFAULT = VERSIONS[0]
