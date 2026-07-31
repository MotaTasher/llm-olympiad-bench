# models/gemini/versions.py
# Source:
#   https://ai.google.dev/gemini-api/docs/models
#   https://ai.google.dev/gemini-api/docs/pricing
#   https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/thinking
# Benchmark snapshot: 2026-08-01

VERSIONS = [
    "gemini-3.5-flash",
]

LEGACY_VERSIONS = ["gemini-3.1-pro-preview"]

DEFAULT = VERSIONS[0]
