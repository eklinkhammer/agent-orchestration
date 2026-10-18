"""Planner agent — creates implementation plans for individual tasks."""

from __future__ import annotations

from sovereign.agents.base import AgentConfig

PLANNER = AgentConfig(
    role="planner",
    permission_mode="plan",
    system_prompt_file="planner.md",
    output_json=False,
)
