# models/claude/versions.py
# Source: https://platform.claude.com/docs/en/about-claude/models/overview
# Source: https://platform.claude.com/docs/en/about-claude/model-deprecations
# Source: https://platform.claude.com/docs/en/api/models/list
# Updated: 2026-06-29

# Keep the scoring UI focused on the strongest active Claude model.

VERSIONS = [
    "claude-opus-4-8",
]

LEGACY_VERSIONS = [
    "claude-haiku-4-5-20251001",
]

DEFAULT = VERSIONS[0]

# Verify with:
# curl https://api.anthropic.com/v1/models \
#   --header "x-api-key: $ANTHROPIC_API_KEY" \
#   --header "anthropic-version: 2023-06-01"
