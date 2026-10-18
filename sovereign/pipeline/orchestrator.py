"""Async orchestrator — polls SQLite for work, spawns agents, advances state."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sovereign.agents.architect import ARCHITECT
from sovereign.agents.base import AgentConfig, AgentRunner, AgentResult
from sovereign.agents.decomposer import DECOMPOSER
from sovereign.agents.implementer import IMPLEMENTER
from sovereign.agents.planner import PLANNER
from sovereign.agents.reviewer import REVIEWER
from sovereign.agents.verifier import VERIFIER
from sovereign.config import Config
from sovereign.db.models import Epic, Task
from sovereign.db.repository import Repository
from sovereign.pipeline.git_manager import GitManager
from sovereign.pipeline.state_machine import (
    EpicStage,
    TaskStage,
    next_epic_stage,
    next_task_stage,
    retry_target,
    EPIC_STAGE_ROLES,
    TASK_STAGE_ROLES,
    TASK_CI_STAGES,
    TASK_GIT_STAGES,
)
from sovereign.testing.runner import TestRunner

log = logging.getLogger(__name__)

# Map role names to agent configs
AGENT_CONFIGS: dict[str, AgentConfig] = {
    "architect": ARCHITECT,
    "decomposer": DECOMPOSER,
    "planner": PLANNER,
    "implementer": IMPLEMENTER,
    "verifier": VERIFIER,
    "reviewer": REVIEWER,
}


class Orchestrator:
    """Main dispatch loop: poll → spawn → advance."""

    def __init__(
        self,
        config: Config,
        repo: Repository,
        git: GitManager,
        runner: AgentRunner,
        test_runner: TestRunner,
    ) -> None:
        self.config = config
        self.repo = repo
        self.git = git
        self.runner = runner
        self.test_runner = test_runner
        self._running = False
        self._active_tasks: set[str] = set()  # IDs currently being processed
        self._semaphore = asyncio.Semaphore(config.max_concurrent_agents)

    async def start(self) -> None:
        """Start the orchestration loop."""
        self._running = True
        log.info("Orchestrator started (poll interval: %.1fs)", self.config.poll_interval)

        try:
            await self.git.ensure_branches()
        except RuntimeError as e:
            log.warning("Git setup skipped: %s", e)

        while self._running:
            try:
                await self._poll_cycle()
            except Exception:
                log.exception("Error in poll cycle")
            await asyncio.sleep(self.config.poll_interval)

    async def stop(self) -> None:
        """Stop the orchestration loop."""
        self._running = False
        log.info("Orchestrator stopping")

    async def _poll_cycle(self) -> None:
        """One poll cycle: find actionable work and dispatch it."""
        # Process epics
        epics = await self.repo.get_actionable_epics()
        for epic in epics:
            key = f"epic:{epic.id}"
            if key not in self._active_tasks:
                stage = EpicStage(epic.stage)
                if stage == EpicStage.BACKLOG:
                    # Auto-advance backlog → designing
                    await self.repo.update_epic_stage(epic.id, EpicStage.DESIGNING)
                elif stage in EPIC_STAGE_ROLES:
                    self._active_tasks.add(key)
                    asyncio.create_task(self._dispatch_epic(epic, key))

        # Process tasks
        tasks = await self.repo.get_actionable_tasks()
        for task in tasks:
            key = f"task:{task.id}"
            if key not in self._active_tasks:
                self._active_tasks.add(key)
                asyncio.create_task(self._dispatch_task(task, key))

    async def _dispatch_epic(self, epic: Epic, key: str) -> None:
        """Dispatch an epic to the appropriate agent."""
        try:
            async with self._semaphore:
                stage = EpicStage(epic.stage)
                role = EPIC_STAGE_ROLES.get(stage)
                if not role:
                    return

                agent_config = AGENT_CONFIGS[role]
                context = await self.repo.get_context_for_stage(epic_id=epic.id)

                log.info("Running %s for epic %s (%s)", role, epic.id, epic.title)
                run = await self.repo.create_agent_run(
                    role=role, stage=stage, prompt=context, epic_id=epic.id,
                )

                result = await self.runner.run(agent_config, context)

                await self.repo.finish_agent_run(
                    run.id, output=result.output, cost_usd=result.cost_usd,
                    input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                    duration_sec=result.duration_sec, session_id=result.session_id,
                )

                await self._handle_epic_result(epic, stage, role, result, run.id)
        except Exception:
            log.exception("Failed to dispatch epic %s", epic.id)
        finally:
            self._active_tasks.discard(key)

    async def _handle_epic_result(
        self, epic: Epic, stage: EpicStage, role: str, result: AgentResult, run_id: str
    ) -> None:
        """Process the result of an epic agent run."""
        if stage == EpicStage.DESIGNING:
            await self.repo.create_artifact(
                kind="design_doc", content=result.output, epic_id=epic.id, run_id=run_id,
            )
            await self.repo.update_epic_stage(epic.id, EpicStage.DECOMPOSING)

        elif stage == EpicStage.DECOMPOSING:
            tasks_data = self._parse_task_list(result)
            if tasks_data:
                await self.repo.create_artifact(
                    kind="task_list", content=json.dumps(tasks_data),
                    epic_id=epic.id, run_id=run_id,
                )
                # Create task rows
                for task_data in tasks_data:
                    await self.repo.create_task(
                        epic_id=epic.id,
                        title=task_data["title"],
                        description=task_data.get("description", ""),
                        dependencies=task_data.get("dependencies"),
                    )
                await self.repo.update_epic_stage(epic.id, EpicStage.READY_FOR_PLANNING)
            else:
                log.error("Decomposer produced invalid output for epic %s", epic.id)

    def _parse_task_list(self, result: AgentResult) -> list[dict[str, Any]] | None:
        """Parse decomposer JSON output into a task list."""
        if result.parsed_json and isinstance(result.parsed_json, dict):
            return result.parsed_json.get("tasks")

        # Try parsing the raw output as JSON
        try:
            data = json.loads(result.output)
            if isinstance(data, dict) and "tasks" in data:
                return data["tasks"]
        except json.JSONDecodeError:
            pass

        return None

    async def _dispatch_task(self, task: Task, key: str) -> None:
        """Dispatch a task to the appropriate handler."""
        try:
            async with self._semaphore:
                stage = TaskStage(task.stage)

                if stage in TASK_STAGE_ROLES:
                    await self._run_agent_for_task(task, stage)
                elif stage in TASK_CI_STAGES:
                    await self._run_ci_for_task(task, stage)
                elif stage in TASK_GIT_STAGES:
                    await self._run_git_for_task(task, stage)
        except Exception:
            log.exception("Failed to dispatch task %s", task.id)
        finally:
            self._active_tasks.discard(key)

    async def _run_agent_for_task(self, task: Task, stage: TaskStage) -> None:
        """Run a Claude agent for a task stage."""
        role = TASK_STAGE_ROLES[stage]
        agent_config = AGENT_CONFIGS[role]
        context = await self.repo.get_context_for_stage(task_id=task.id, epic_id=task.epic_id)

        log.info("Running %s for task %s (%s)", role, task.id, task.title)

        # Ensure worktree exists for implementer
        if stage == TaskStage.IMPLEMENTING and not task.worktree_path:
            branch_name, worktree_path = await self.git.create_task_branch(task.id, task.title)
            await self.repo.update_task_branch(task.id, branch_name, worktree_path)
            task.branch_name = branch_name
            task.worktree_path = worktree_path

        run = await self.repo.create_agent_run(
            role=role, stage=stage, prompt=context, task_id=task.id, epic_id=task.epic_id,
        )

        cwd = task.worktree_path if stage == TaskStage.IMPLEMENTING else None
        result = await self.runner.run(agent_config, context, cwd=cwd)

        await self.repo.finish_agent_run(
            run.id, output=result.output, cost_usd=result.cost_usd,
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
            duration_sec=result.duration_sec, session_id=result.session_id,
        )

        await self._handle_task_result(task, stage, role, result, run.id)

    async def _handle_task_result(
        self, task: Task, stage: TaskStage, role: str, result: AgentResult, run_id: str
    ) -> None:
        """Process the result of a task agent run and advance state."""
        if stage == TaskStage.PLANNING:
            await self.repo.create_artifact(
                kind="implementation_plan", content=result.output,
                task_id=task.id, epic_id=task.epic_id, run_id=run_id,
            )
            await self.repo.update_task_stage(task.id, next_task_stage(stage))

        elif stage == TaskStage.IMPLEMENTING:
            # Capture the diff as an artifact
            diff = "(no worktree)" if not task.worktree_path else await self.git.get_diff(task.worktree_path)
            await self.repo.create_artifact(
                kind="code_diff", content=diff,
                task_id=task.id, epic_id=task.epic_id, run_id=run_id,
            )
            await self.repo.update_task_stage(task.id, next_task_stage(stage))

        elif stage == TaskStage.VERIFYING:
            await self.repo.create_artifact(
                kind="verification_report", content=result.output,
                task_id=task.id, epic_id=task.epic_id, run_id=run_id,
            )
            conforms = self._check_verification(result)
            if conforms:
                await self.repo.update_task_stage(task.id, next_task_stage(stage))
            else:
                await self._retry_or_fail(task, stage, "Verification gaps found")

        elif stage == TaskStage.REVIEWING:
            await self.repo.create_artifact(
                kind="review_report", content=result.output,
                task_id=task.id, epic_id=task.epic_id, run_id=run_id,
            )
            approved = self._check_review(result)
            if approved:
                await self.repo.update_task_stage(task.id, next_task_stage(stage))
            else:
                await self._retry_or_fail(task, stage, "Review requested revisions")

    def _check_verification(self, result: AgentResult) -> bool:
        """Check if verification passed."""
        if result.parsed_json and isinstance(result.parsed_json, dict):
            return result.parsed_json.get("conforms", False)
        try:
            data = json.loads(result.output)
            return data.get("conforms", False)
        except (json.JSONDecodeError, AttributeError):
            return False

    def _check_review(self, result: AgentResult) -> bool:
        """Check if review approved."""
        if result.parsed_json and isinstance(result.parsed_json, dict):
            return result.parsed_json.get("verdict") == "approve"
        try:
            data = json.loads(result.output)
            return data.get("verdict") == "approve"
        except (json.JSONDecodeError, AttributeError):
            return False

    async def _run_ci_for_task(self, task: Task, stage: TaskStage) -> None:
        """Run CI tests for a task."""
        log.info("Running CI %s for task %s", stage, task.id)

        if stage == TaskStage.UNIT_TESTING:
            success, output = await self.test_runner.run_unit_tests()
        elif stage == TaskStage.INTEGRATION_TESTING:
            success, output = await self.test_runner.run_integration_tests()
        elif stage == TaskStage.DOCKER_E2E_TESTING:
            success, output = await self.test_runner.run_e2e_tests()
        else:
            return

        await self.repo.create_artifact(
            kind="test_result", content=output,
            task_id=task.id, epic_id=task.epic_id,
        )

        if success:
            await self.repo.update_task_stage(task.id, next_task_stage(stage))
        else:
            await self._retry_or_fail(task, stage, f"CI {stage} failed")

    async def _run_git_for_task(self, task: Task, stage: TaskStage) -> None:
        """Run git operations for a task."""
        log.info("Running git %s for task %s", stage, task.id)

        if stage == TaskStage.MERGING_TO_DEV:
            if task.branch_name:
                try:
                    await self.git.merge_to_dev(task.branch_name)
                    await self.repo.update_task_stage(task.id, next_task_stage(stage))
                except RuntimeError as e:
                    await self._retry_or_fail(task, stage, f"Merge to dev failed: {e}")
            else:
                log.error("Task %s has no branch name for merge", task.id)
                await self.repo.update_task_stage(task.id, TaskStage.FAILED, "No branch name")

        elif stage == TaskStage.READY_FOR_MASTER:
            # This is handled at the epic level — when all tasks are ready
            pass

    async def _retry_or_fail(self, task: Task, stage: TaskStage, reason: str) -> None:
        """Retry by sending back to implementing, or fail if max retries exceeded."""
        retry_count = await self.repo.increment_retry(task.id)
        target = retry_target(stage)

        if retry_count >= self.config.max_retries or not target:
            log.warning("Task %s failed after %d retries: %s", task.id, retry_count, reason)
            await self.repo.update_task_stage(task.id, TaskStage.FAILED, reason)
        else:
            log.info("Retrying task %s (%d/%d): %s", task.id, retry_count, self.config.max_retries, reason)
            await self.repo.update_task_stage(task.id, target, f"Retry {retry_count}: {reason}")
