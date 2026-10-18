"""Configuration and paths for the sovereign orchestration pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Pipeline configuration with sensible defaults."""

    # Root project directory (where the target repo lives)
    project_root: Path = field(default_factory=lambda: Path.cwd())

    # SQLite database path
    db_path: Path = field(default_factory=lambda: Path.cwd() / "sovereign.db")

    # Directory for git worktrees
    worktree_dir: Path = field(default_factory=lambda: Path.cwd() / "worktrees")

    # Directory for prompt templates
    prompts_dir: Path = field(
        default_factory=lambda: Path(__file__).parent.parent / "prompts"
    )

    # Orchestrator polling interval (seconds)
    poll_interval: float = 2.0

    # TUI refresh interval (seconds)
    tui_refresh_interval: float = 1.0

    # Max retries for failed CI gates
    max_retries: int = 3

    # Claude model to use
    model: str = "sonnet"

    # Long-lived branch names
    master_branch: str = "master"
    dev_branch: str = "dev"

    # Max concurrent agent processes
    max_concurrent_agents: int = 4

    def ensure_dirs(self) -> None:
        """Create required directories if they don't exist."""
        self.worktree_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
