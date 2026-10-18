"""Tests for the orchestrator dispatch logic."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sovereign.agents.base import AgentResult
from sovereign.config import Config
from sovereign.db.schema import init_db
from sovereign.db.repository import Repository
from sovereign.pipeline.git_manager import GitManager
from sovereign.pipeline.orchestrator import Orchestrator
from sovereign.agents.base import AgentRunner
from sovereign.pipeline.state_machine import EpicStage, TaskStage
from sovereign.testing.runner import TestRunner


@pytest.fixture
async def setup(tmp_path):
    """Create orchestrator with mocked agent runner."""
    config = Config(
        project_root=tmp_path,
        db_path=tmp_path / "test.db",
        worktree_dir=tmp_path / "worktrees",
        prompts_dir=tmp_path / "prompts",
        poll_interval=0.1,
    )
    config.ensure_dirs()
    db = await init_db(str(config.db_path))
    repo = Repository(db)
    git = MagicMock(spec=GitManager)
    git.ensure_branches = AsyncMock()
    git.create_task_branch = AsyncMock(return_value=("task/abc-test", str(tmp_path / "wt")))
    git.get_diff = AsyncMock(return_value="diff content")
    git.merge_to_dev = AsyncMock()
    runner = MagicMock(spec=AgentRunner)
    test_runner = MagicMock(spec=TestRunner)
    orchestrator = Orchestrator(config, repo, git, runner, test_runner)
    yield orchestrator, repo, runner, git, test_runner
    await db.close()


class TestEpicDispatch:
    async def test_backlog_auto_advances_to_designing(self, setup) -> None:
        orch, repo, runner, _, _ = setup
        epic = await repo.create_epic("Test Epic", "Description")
        assert epic.stage == EpicStage.BACKLOG

        await orch._poll_cycle()
        updated = await repo.get_epic(epic.id)
        assert updated is not None
        assert updated.stage == EpicStage.DESIGNING

    async def test_designing_dispatches_architect(self, setup) -> None:
        orch, repo, runner, _, _ = setup
        epic = await repo.create_epic("Test Epic")
        await repo.update_epic_stage(epic.id, EpicStage.DESIGNING)

        runner.run = AsyncMock(return_value=AgentResult(
            output="# Design Document\nArchitecture here"
        ))

        await orch._poll_cycle()
        # Wait for the background task
        import asyncio
        await asyncio.sleep(0.2)

        runner.run.assert_called_once()
        updated = await repo.get_epic(epic.id)
        assert updated is not None
        assert updated.stage == EpicStage.DECOMPOSING

    async def test_decomposing_creates_tasks(self, setup) -> None:
        orch, repo, runner, _, _ = setup
        epic = await repo.create_epic("Test Epic")
        await repo.update_epic_stage(epic.id, EpicStage.DECOMPOSING)
        await repo.create_artifact(
            kind="design_doc", content="Design here", epic_id=epic.id
        )

        task_json = json.dumps({
            "tasks": [
                {"title": "Task 1", "description": "Do thing 1", "dependencies": []},
                {"title": "Task 2", "description": "Do thing 2", "dependencies": ["Task 1"]},
            ]
        })
        runner.run = AsyncMock(return_value=AgentResult(
            output=task_json, is_json=True,
            parsed_json=json.loads(task_json),
        ))

        await orch._poll_cycle()
        import asyncio
        await asyncio.sleep(0.2)

        tasks = await repo.get_tasks_by_epic(epic.id)
        assert len(tasks) == 2
        assert tasks[0].title == "Task 1"


class TestTaskDispatch:
    async def test_planning_dispatches_planner(self, setup) -> None:
        orch, repo, runner, _, _ = setup
        epic = await repo.create_epic("Epic")
        task = await repo.create_task(epic.id, "Test Task")

        runner.run = AsyncMock(return_value=AgentResult(
            output="# Implementation Plan\nStep 1..."
        ))

        await orch._poll_cycle()
        import asyncio
        await asyncio.sleep(0.2)

        updated = await repo.get_task(task.id)
        assert updated is not None
        assert updated.stage == TaskStage.IMPLEMENTING

    async def test_verification_pass_advances(self, setup) -> None:
        orch, repo, runner, _, _ = setup
        epic = await repo.create_epic("Epic")
        task = await repo.create_task(epic.id, "Test Task")
        await repo.update_task_stage(task.id, TaskStage.VERIFYING)
        await repo.create_artifact(
            kind="implementation_plan", content="plan", task_id=task.id
        )
        await repo.create_artifact(
            kind="code_diff", content="diff", task_id=task.id
        )

        verify_result = json.dumps({"conforms": True, "gaps": []})
        runner.run = AsyncMock(return_value=AgentResult(
            output=verify_result, is_json=True,
            parsed_json=json.loads(verify_result),
        ))

        await orch._poll_cycle()
        import asyncio
        await asyncio.sleep(0.2)

        updated = await repo.get_task(task.id)
        assert updated is not None
        assert updated.stage == TaskStage.REVIEWING

    async def test_verification_fail_retries(self, setup) -> None:
        orch, repo, runner, _, _ = setup
        epic = await repo.create_epic("Epic")
        task = await repo.create_task(epic.id, "Test Task")
        await repo.update_task_stage(task.id, TaskStage.VERIFYING)

        verify_result = json.dumps({
            "conforms": False,
            "gaps": [{"item": "Missing feature", "description": "Not implemented"}]
        })
        runner.run = AsyncMock(return_value=AgentResult(
            output=verify_result, is_json=True,
            parsed_json=json.loads(verify_result),
        ))

        await orch._poll_cycle()
        import asyncio
        await asyncio.sleep(0.2)

        updated = await repo.get_task(task.id)
        assert updated is not None
        assert updated.stage == TaskStage.IMPLEMENTING  # retried

    async def test_review_approve_advances(self, setup) -> None:
        orch, repo, runner, _, _ = setup
        epic = await repo.create_epic("Epic")
        task = await repo.create_task(epic.id, "Test Task")
        await repo.update_task_stage(task.id, TaskStage.REVIEWING)

        review_result = json.dumps({"verdict": "approve", "issues": []})
        runner.run = AsyncMock(return_value=AgentResult(
            output=review_result, is_json=True,
            parsed_json=json.loads(review_result),
        ))

        await orch._poll_cycle()
        import asyncio
        await asyncio.sleep(0.2)

        updated = await repo.get_task(task.id)
        assert updated is not None
        assert updated.stage == TaskStage.MERGING_TO_DEV

    async def test_max_retries_leads_to_failure(self, setup) -> None:
        orch, repo, runner, _, _ = setup
        orch.config = Config(
            project_root=orch.config.project_root,
            db_path=orch.config.db_path,
            max_retries=1,
            poll_interval=0.1,
        )

        epic = await repo.create_epic("Epic")
        task = await repo.create_task(epic.id, "Test Task")
        await repo.update_task_stage(task.id, TaskStage.VERIFYING)
        # Already at 1 retry
        await repo.increment_retry(task.id)

        verify_result = json.dumps({"conforms": False, "gaps": [{"item": "x", "description": "y"}]})
        runner.run = AsyncMock(return_value=AgentResult(
            output=verify_result, is_json=True,
            parsed_json=json.loads(verify_result),
        ))

        await orch._poll_cycle()
        import asyncio
        await asyncio.sleep(0.2)

        updated = await repo.get_task(task.id)
        assert updated is not None
        assert updated.stage == TaskStage.FAILED
