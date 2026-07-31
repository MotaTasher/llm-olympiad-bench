# models/claude/versions.py
# Source: https://platform.claude.com/docs/en/about-claude/models/overview
# Source: https://platform.claude.com/docs/en/about-claude/model-deprecations
# Source: https://platform.claude.com/docs/en/api/models/list
# Updated: 2026-07-31

# Anthropic is the one provider with two active benchmark columns: the
# strongest Opus and the current Haiku comparison model.

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
