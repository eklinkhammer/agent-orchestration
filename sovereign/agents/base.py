"""Base agent runner — subprocess invocation for Claude Code CLI."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sovereign.config import Config


@dataclass
class AgentResult:
    """Result from a Claude Code CLI invocation."""

    output: str
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_sec: float | None = None
    session_id: str | None = None
    is_json: bool = False
    parsed_json: dict[str, Any] | None = None


@dataclass
class AgentConfig:
    """Configuration for an agent role."""

    role: str
    permission_mode: str  # "plan" or "allowEdits"
    system_prompt_file: str  # filename in prompts/ directory
    output_json: bool = False  # whether to request JSON output


class AgentRunner:
    """Runs Claude Code CLI as a subprocess with role-specific configuration."""

    def __init__(self, config: Config) -> None:
        self.config = config

    async def run(
        self,
        agent_config: AgentConfig,
        context: str,
        cwd: str | None = None,
    ) -> AgentResult:
        """Invoke claude CLI with the given agent configuration and context."""
        system_prompt = self._load_system_prompt(agent_config.system_prompt_file)

        cmd = [
            "claude",
            "-p", context,
            "--system-prompt", system_prompt,
            "--model", self.config.model,
            "--permission-mode", agent_config.permission_mode,
        ]

        if agent_config.output_json:
            cmd.extend(["--output-format", "json"])

        work_dir = cwd or str(self.config.project_root)

        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        duration = time.monotonic() - start

        output_text = stdout.decode("utf-8", errors="replace")
        result = AgentResult(output=output_text, duration_sec=duration)

        # Try to parse JSON output for structured agents
        if agent_config.output_json:
            try:
                parsed = json.loads(output_text)
                result.is_json = True
                result.parsed_json = parsed
                # Extract cost/token info if present in JSON wrapper
                if isinstance(parsed, dict):
                    result.cost_usd = parsed.get("cost_usd")
                    result.input_tokens = parsed.get("input_tokens")
                    result.output_tokens = parsed.get("output_tokens")
                    result.session_id = parsed.get("session_id")
                    # The actual result might be nested
                    if "result" in parsed:
                        result.output = (
                            json.dumps(parsed["result"])
                            if isinstance(parsed["result"], dict)
                            else str(parsed["result"])
                        )
                        result.parsed_json = parsed["result"] if isinstance(parsed["result"], dict) else parsed
            except json.JSONDecodeError:
                result.is_json = False

        if proc.returncode != 0 and not output_text.strip():
            stderr_text = stderr.decode("utf-8", errors="replace")
            result.output = f"Agent failed (exit {proc.returncode}): {stderr_text}"

        return result

    def _load_system_prompt(self, filename: str) -> str:
        """Load a system prompt from the prompts directory."""
        prompt_path = self.config.prompts_dir / filename
        if prompt_path.exists():
            return prompt_path.read_text()
        return f"You are a {filename.replace('.md', '')} agent."
