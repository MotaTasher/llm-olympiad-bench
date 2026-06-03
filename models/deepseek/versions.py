# models/deepseek/versions.py
# Source:
#   https://api-docs.deepseek.com/api/list-models
#   https://api-docs.deepseek.com/quick_start/pricing
#   https://api-docs.deepseek.com/updates/
# Updated: 2026-06-03
#
# Programmatic check:
#   curl https://api.deepseek.com/models \
#     -H "Authorization: Bearer $DEEPSEEK_API_KEY"

VERSIONS = [
    "deepseek-v4-pro",
    "deepseek-v4-flash",
]

LEGACY_VERSIONS = [
    # Deprecated on 2026-07-24 according to official change log.
    # Currently map to non-thinking/thinking mode of deepseek-v4-flash.
    "deepseek-chat",
    "deepseek-reasoner",
]

DEFAULT = VERSIONS[0]
