# models/yandexgpt/versions.py
# Source: https://aistudio.yandex.ru/docs/en/ai-studio/concepts/generation/models
# Source: https://aistudio.yandex.ru/docs/en/ai-studio/operations/models/get
# Updated: 2026-06-29
#
# Model IDs are URI suffixes. Build full modelUri as:
#     f"gpt://{YANDEX_FOLDER_ID}/{model_id}"
#
# Programmatic check:
#     curl https://ai.api.cloud.yandex.net/v1/models \
#       --header "Authorization: Api-Key <API_key>" \
#       --header "x-project: <folder_ID>"
#
# Python check:
#     import openai
#     client = openai.OpenAI(
#         api_key=YANDEX_API_KEY,
#         base_url="https://ai.api.cloud.yandex.net/v1",
#         project=YANDEX_FOLDER_ID,
#     )
#     for model in client.models.list().data:
#         print(model.id)
#
# Access notes:
# - Requires a service account with ai.languageModels.user or higher.
# - API key should have yc.ai.foundationModels.execute scope.
# - Available models may depend on folder, billing status, quotas, and enabled features.

VERSIONS = [
    # Strongest current YandexGPT model for this completion adapter.
    "yandexgpt-5.1",

    # Strongest budget/free-tier YandexGPT model for this completion adapter.
    "yandexgpt-5-lite",
]

LEGACY_VERSIONS = []

DEFAULT = VERSIONS[0]
