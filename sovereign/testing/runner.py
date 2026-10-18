"""Test runners for CI pipeline stages."""

from __future__ import annotations

import asyncio

from sovereign.config import Config


class TestRunner:
    """Runs pytest and other test commands as part of the CI pipeline."""

    def __init__(self, config: Config) -> None:
        self.config = config

    async def _run_command(self, *args: str, cwd: str | None = None) -> tuple[bool, str]:
        """Run a command and return (success, output)."""
        work_dir = cwd or str(self.config.project_root)
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")
        return proc.returncode == 0, output

    async def run_unit_tests(self, cwd: str | None = None) -> tuple[bool, str]:
        """Run unit tests with pytest."""
        return await self._run_command(
            "python", "-m", "pytest", "tests/", "-v", "--tb=short", "-q",
            "-m", "not integration and not e2e",
            cwd=cwd,
        )

    async def run_integration_tests(self, cwd: str | None = None) -> tuple[bool, str]:
        """Run integration tests with pytest."""
        return await self._run_command(
            "python", "-m", "pytest", "tests/", "-v", "--tb=short", "-q",
            "-m", "integration",
            cwd=cwd,
        )

    async def run_e2e_tests(self, cwd: str | None = None) -> tuple[bool, str]:
        """Run E2E tests using docker-compose."""
        from sovereign.testing.docker_e2e import DockerE2ERunner
        runner = DockerE2ERunner(self.config)
        return await runner.run(cwd=cwd)
