# models/gigachat/versions.py
# Source:
# - https://developers.sber.ru/docs/ru/gigachat/models/main
# - https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/get-models
# - https://developers.sber.ru/docs/ru/gigachat/guides/preview-models
# - https://developers.sber.ru/docs/ru/gigachat/tariffs/individual-tariffs
# Updated: 2026-07-31

VERSIONS = [
    # Strongest paid production model.
    "GigaChat-2-Max",
]

LEGACY_VERSIONS = ["GigaChat-2"]

DEFAULT = VERSIONS[0]
