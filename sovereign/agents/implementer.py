"""Implementer agent — writes code, runs build/test/typecheck/lint."""

from __future__ import annotations

from sovereign.agents.base import AgentConfig

IMPLEMENTER = AgentConfig(
    role="implementer",
    permission_mode="allowEdits",
    system_prompt_file="implementer.md",
    output_json=False,
)
