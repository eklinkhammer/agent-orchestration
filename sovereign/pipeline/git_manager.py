"""Git branch and worktree management."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from sovereign.config import Config


class GitManager:
    """Manages git branches and worktrees for the pipeline."""

    def __init__(self, config: Config) -> None:
        self.config = config

    async def _run(self, *args: str, cwd: str | None = None) -> str:
        """Run a git command and return stdout."""
        work_dir = cwd or str(self.config.project_root)
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"git {' '.join(args)} failed: {err}")
        return stdout.decode("utf-8", errors="replace").strip()

    async def ensure_branches(self) -> None:
        """Ensure master and dev branches exist."""
        branches = await self._run("branch", "--list")
        branch_names = {b.strip().lstrip("* ") for b in branches.splitlines()}

        if self.config.master_branch not in branch_names:
            # If no commits yet, create initial commit
            try:
                await self._run("rev-parse", "HEAD")
            except RuntimeError:
                await self._run("commit", "--allow-empty", "-m", "Initial commit")
            # Rename or ensure master exists
            if "main" in branch_names and self.config.master_branch not in branch_names:
                await self._run("branch", "-m", "main", self.config.master_branch)

        if self.config.dev_branch not in branch_names:
            await self._run("branch", self.config.dev_branch, self.config.master_branch)

    def _slugify(self, text: str) -> str:
        """Convert text to a git-safe slug."""
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
        return slug[:40]

    async def create_task_branch(self, task_id: str, title: str) -> tuple[str, str]:
        """Create a feature branch and worktree for a task.

        Returns (branch_name, worktree_path).
        """
        slug = self._slugify(title)
        branch_name = f"task/{task_id}-{slug}"
        worktree_path = str(self.config.worktree_dir / f"{task_id}-{slug}")

        # Create the worktree with a new branch off dev
        await self._run(
            "worktree", "add", "-b", branch_name, worktree_path, self.config.dev_branch
        )

        return branch_name, worktree_path

    async def get_diff(self, worktree_path: str) -> str:
        """Get the diff of uncommitted + committed changes vs dev in a worktree."""
        # Get diff of all changes (staged + unstaged + committed) compared to dev
        try:
            diff = await self._run(
                "diff", f"{self.config.dev_branch}...HEAD", cwd=worktree_path
            )
        except RuntimeError:
            diff = ""

        # Also get uncommitted changes
        try:
            uncommitted = await self._run("diff", "HEAD", cwd=worktree_path)
        except RuntimeError:
            uncommitted = ""

        parts = []
        if diff:
            parts.append(f"Committed changes vs {self.config.dev_branch}:\n{diff}")
        if uncommitted:
            parts.append(f"Uncommitted changes:\n{uncommitted}")
        return "\n\n".join(parts) if parts else "(no changes)"

    async def merge_to_dev(self, branch_name: str) -> str:
        """Fast-forward merge a feature branch into dev."""
        # Checkout dev
        await self._run("checkout", self.config.dev_branch)
        try:
            result = await self._run("merge", "--ff-only", branch_name)
            return result
        finally:
            # Go back to master (don't leave repo on dev)
            await self._run("checkout", self.config.master_branch)

    async def merge_dev_to_master(self) -> str:
        """Merge dev into master."""
        await self._run("checkout", self.config.master_branch)
        result = await self._run("merge", "--ff-only", self.config.dev_branch)
        return result

    async def cleanup_worktree(self, worktree_path: str, branch_name: str) -> None:
        """Remove a worktree and its branch."""
        try:
            await self._run("worktree", "remove", worktree_path, "--force")
        except RuntimeError:
            pass  # worktree may already be gone
        try:
            await self._run("branch", "-d", branch_name)
        except RuntimeError:
            pass  # branch may already be gone
