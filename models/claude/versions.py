# models/claude/versions.py
# Source: https://platform.claude.com/docs/en/about-claude/models/overview
# Source: https://platform.claude.com/docs/en/about-claude/model-deprecations
# Source: https://platform.claude.com/docs/en/api/models/list
# Updated: 2026-06-03

VERSIONS = [
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-opus-4-5-20251101",
    "claude-opus-4-1-20250805",
    "claude-sonnet-4-6",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
]

LEGACY_VERSIONS = [
    # Deprecated on 2026-04-14, scheduled retirement: 2026-06-15.
    "claude-opus-4-20250514",
    "claude-sonnet-4-20250514",
]

DEFAULT = VERSIONS[0]

# Verify with:
# curl https://api.anthropic.com/v1/models \
#   --header "x-api-key: $ANTHROPIC_API_KEY" \
#   --header "anthropic-version: 2023-06-01"