"""Reviewer agent — code quality review (JSON output)."""

from __future__ import annotations

from sovereign.agents.base import AgentConfig

REVIEWER = AgentConfig(
    role="reviewer",
    permission_mode="plan",
    system_prompt_file="reviewer.md",
    output_json=True,
)

# Expected JSON schema for reviewer output:
# {
#   "verdict": "approve"|"revise",
#   "issues": [
#     {"severity": "critical"|"major"|"minor", "description": "string", "file": "string", "line": int}
#   ]
# }
