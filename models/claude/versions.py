# models/claude/versions.py
# Source: https://platform.claude.com/docs/en/about-claude/models/overview
# Source: https://platform.claude.com/docs/en/about-claude/model-deprecations
# Source: https://platform.claude.com/docs/en/api/models/list
# Benchmark snapshot: 2026-08-01

# Anthropic is the one provider with two active benchmark columns: the
# strongest generally available model and the strongest Opus model.

VERSIONS = [
    "claude-fable-5",
    "claude-opus-5",
]

LEGACY_VERSIONS = [
    "claude-opus-4-8",
    "claude-haiku-4-5-20251001",
]

DEFAULT = VERSIONS[0]

# Verify with:
# curl https://api.anthropic.com/v1/models \
#   --header "x-api-key: $ANTHROPIC_API_KEY" \
#   --header "anthropic-version: 2023-06-01"
