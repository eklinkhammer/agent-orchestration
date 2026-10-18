"""Decomposer agent — breaks design docs into task lists (JSON output)."""

from __future__ import annotations

from sovereign.agents.base import AgentConfig

DECOMPOSER = AgentConfig(
    role="decomposer",
    permission_mode="plan",
    system_prompt_file="decomposer.md",
    output_json=True,
)

# Expected JSON schema for decomposer output:
# {
#   "tasks": [
#     {
#       "title": "string",
#       "description": "string",
#       "dependencies": ["task_title_1", ...]
#     }
#   ]
# }
