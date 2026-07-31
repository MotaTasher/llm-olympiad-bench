# models/yandexgpt/versions.py
# Source: https://aistudio.yandex.ru/docs/en/ai-studio/concepts/generation/models
# Source: https://aistudio.yandex.ru/docs/en/ai-studio/operations/models/get
# Benchmark snapshot: 2026-08-01
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
    # Yandex's current flagship text model; uses the same completion adapter.
    "aliceai-llm",
]

LEGACY_VERSIONS = ["yandexgpt-5.1", "yandexgpt-5-lite"]

DEFAULT = VERSIONS[0]
