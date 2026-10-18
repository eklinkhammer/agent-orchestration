"""Verifier agent — checks implementation conformance to plan (JSON output)."""

from __future__ import annotations

from sovereign.agents.base import AgentConfig

VERIFIER = AgentConfig(
    role="verifier",
    permission_mode="plan",
    system_prompt_file="verifier.md",
    output_json=True,
)

# Expected JSON schema for verifier output:
# {
#   "conforms": true|false,
#   "gaps": [
#     {"item": "string", "description": "string"}
#   ]
# }
