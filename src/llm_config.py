"""Central LLM model version configuration.

All model version strings are pinned here. Consumer modules import
from this file so that upgrades require exactly one change.
"""

# Anthropic Claude model versions — update here when upgrading
SONNET_MODEL = "claude-sonnet-4-20250514"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Alias kept for backward compatibility — all Haiku consumers now use the same model
HAIKU_LEGACY_MODEL = HAIKU_MODEL
