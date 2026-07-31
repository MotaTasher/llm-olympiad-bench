# models/gigachat/versions.py
# Source:
# - https://developers.sber.ru/docs/ru/gigachat/models/main
# - https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/get-models
# - https://developers.sber.ru/docs/ru/gigachat/guides/preview-models
# - https://developers.sber.ru/docs/ru/gigachat/tariffs/individual-tariffs
# Benchmark snapshot: 2026-08-01

VERSIONS = [
    # Strongest paid production model.
    "GigaChat-3-Ultra",
]

LEGACY_VERSIONS = ["GigaChat-2-Max", "GigaChat-2"]

DEFAULT = VERSIONS[0]
