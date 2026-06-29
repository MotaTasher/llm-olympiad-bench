# models/deepseek/versions.py
# Source:
#   https://api-docs.deepseek.com/api/list-models
#   https://api-docs.deepseek.com/quick_start/pricing
#   https://api-docs.deepseek.com/updates/
# Updated: 2026-06-29
#
# Programmatic check:
#   curl https://api.deepseek.com/models \
#     -H "Authorization: Bearer $DEEPSEEK_API_KEY"

VERSIONS = [
    # Strongest paid model.
    "deepseek-v4-pro",

    # Strongest budget/free-tier candidate available through this adapter.
    "deepseek-v4-flash",
]

LEGACY_VERSIONS = []

DEFAULT = VERSIONS[0]
