"""Central LLM model version configuration.

All model version strings are pinned here. Consumer modules import
from this file so that upgrades require exactly one change.
"""

# Anthropic Claude model versions — update here when upgrading
SONNET_MODEL = "claude-sonnet-4-20250514"
HAIKU_MODEL = "claude-3-5-haiku-20241022"

# Legacy model kept for state classifier (older Haiku)
HAIKU_LEGACY_MODEL = "claude-3-haiku-20240307"
