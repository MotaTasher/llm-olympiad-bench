# models/deepseek/versions.py
# Source:
#   https://api-docs.deepseek.com/api/list-models
#   https://api-docs.deepseek.com/quick_start/pricing
#   https://api-docs.deepseek.com/updates/
# Benchmark snapshot: 2026-08-01
#
# Programmatic check:
#   curl https://api.deepseek.com/models \
#     -H "Authorization: Bearer $DEEPSEEK_API_KEY"

VERSIONS = [
    # Strongest paid model.
    "deepseek-v4-pro",
]

LEGACY_VERSIONS = ["deepseek-v4-flash"]

DEFAULT = VERSIONS[0]
