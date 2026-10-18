"""Docker-based E2E test runner."""

from __future__ import annotations

import asyncio

from sovereign.config import Config


class DockerE2ERunner:
    """Runs E2E tests using docker-compose."""

    def __init__(self, config: Config) -> None:
        self.config = config

    async def run(self, cwd: str | None = None) -> tuple[bool, str]:
        """Build and run E2E tests in Docker.

        Returns (success, output).
        """
        work_dir = cwd or str(self.config.project_root)

        # Step 1: Build
        build_proc = await asyncio.create_subprocess_exec(
            "docker-compose", "build",
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        build_out, _ = await build_proc.communicate()
        build_output = build_out.decode("utf-8", errors="replace")

        if build_proc.returncode != 0:
            return False, f"Docker build failed:\n{build_output}"

        # Step 2: Run tests
        test_proc = await asyncio.create_subprocess_exec(
            "docker-compose", "run", "--rm", "test",
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        test_out, _ = await test_proc.communicate()
        test_output = test_out.decode("utf-8", errors="replace")

        # Step 3: Cleanup
        cleanup_proc = await asyncio.create_subprocess_exec(
            "docker-compose", "down", "--volumes",
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        await cleanup_proc.communicate()

        full_output = f"Build:\n{build_output}\n\nTests:\n{test_output}"
        return test_proc.returncode == 0, full_output
