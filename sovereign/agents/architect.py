"""Architect agent — produces design documents from epic descriptions."""

from __future__ import annotations

from sovereign.agents.base import AgentConfig

ARCHITECT = AgentConfig(
    role="architect",
    permission_mode="plan",
    system_prompt_file="architect.md",
    output_json=False,
)
