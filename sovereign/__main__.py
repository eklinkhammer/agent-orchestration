"""Entry point for the sovereign orchestration pipeline."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sovereign.config import Config
from sovereign.db.schema import init_db
from sovereign.db.repository import Repository
from sovereign.pipeline.git_manager import GitManager
from sovereign.pipeline.orchestrator import Orchestrator
from sovereign.agents.base import AgentRunner
from sovereign.testing.runner import TestRunner


async def run_orchestrator_only(config: Config) -> None:
    """Run the orchestrator without the TUI."""
    db = await init_db(str(config.db_path))
    repo = Repository(db)
    git = GitManager(config)
    runner = AgentRunner(config)
    test_runner = TestRunner(config)
    orchestrator = Orchestrator(config, repo, git, runner, test_runner)

    try:
        await orchestrator.start()
    except asyncio.CancelledError:
        await orchestrator.stop()
    finally:
        await db.close()


async def run_with_tui(config: Config) -> None:
    """Run the orchestrator alongside the TUI."""
    db = await init_db(str(config.db_path))
    repo = Repository(db)
    git = GitManager(config)
    runner = AgentRunner(config)
    test_runner = TestRunner(config)
    orchestrator = Orchestrator(config, repo, git, runner, test_runner)

    from sovereign.tui.app import SovereignApp

    app = SovereignApp(config=config, repo=repo, orchestrator=orchestrator)
    await app.run_async()
    await db.close()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="sovereign",
        description="Sovereign Tech — Agent orchestration pipeline",
    )
    parser.add_argument(
        "--no-tui", action="store_true",
        help="Run orchestrator only (no terminal UI)",
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--project-root", type=str, default=None,
        help="Path to the target project root",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = Config()
    if args.db:
        from pathlib import Path
        config = Config(db_path=Path(args.db))
    if args.project_root:
        from pathlib import Path
        config = Config(
            project_root=Path(args.project_root),
            db_path=config.db_path,
        )

    config.ensure_dirs()

    if args.no_tui:
        asyncio.run(run_orchestrator_only(config))
    else:
        asyncio.run(run_with_tui(config))


if __name__ == "__main__":
    main()
