# models/claude/versions.py
# Source: https://platform.claude.com/docs/en/about-claude/models/overview
# Source: https://platform.claude.com/docs/en/about-claude/model-deprecations
# Source: https://platform.claude.com/docs/en/api/models/list
# Updated: 2026-06-29

# Keep the scoring UI focused: strongest paid Claude plus the strongest
# budget/Haiku Claude. Anthropic API access is billed by usage; there is no
# separate free API model ID in this adapter.

VERSIONS = [
    "claude-opus-4-8",
    "claude-haiku-4-5-20251001",
]

LEGACY_VERSIONS = []

DEFAULT = VERSIONS[0]

# Verify with:
# curl https://api.anthropic.com/v1/models \
#   --header "x-api-key: $ANTHROPIC_API_KEY" \
#   --header "anthropic-version: 2023-06-01"
