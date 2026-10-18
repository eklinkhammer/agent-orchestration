"""Tests for the database repository."""

import pytest

from sovereign.db.schema import init_db
from sovereign.db.repository import Repository
from sovereign.pipeline.state_machine import EpicStage, TaskStage


@pytest.fixture
async def repo(tmp_path):
    """Create a repository with an in-memory-like temp database."""
    db_path = str(tmp_path / "test.db")
    db = await init_db(db_path)
    yield Repository(db)
    await db.close()


class TestEpicCRUD:
    async def test_create_epic(self, repo: Repository) -> None:
        epic = await repo.create_epic("Test Epic", "A test description")
        assert epic.title == "Test Epic"
        assert epic.stage == EpicStage.BACKLOG

    async def test_get_epic(self, repo: Repository) -> None:
        created = await repo.create_epic("Test Epic")
        fetched = await repo.get_epic(created.id)
        assert fetched is not None
        assert fetched.title == "Test Epic"

    async def test_get_nonexistent_epic(self, repo: Repository) -> None:
        result = await repo.get_epic("nonexistent")
        assert result is None

    async def test_update_epic_stage(self, repo: Repository) -> None:
        epic = await repo.create_epic("Test Epic")
        await repo.update_epic_stage(epic.id, EpicStage.DESIGNING)
        updated = await repo.get_epic(epic.id)
        assert updated is not None
        assert updated.stage == EpicStage.DESIGNING

    async def test_get_epics_by_stage(self, repo: Repository) -> None:
        await repo.create_epic("Epic 1")
        await repo.create_epic("Epic 2")
        epics = await repo.get_epics_by_stage(EpicStage.BACKLOG)
        assert len(epics) == 2

    async def test_get_all_epics(self, repo: Repository) -> None:
        await repo.create_epic("Epic 1")
        await repo.create_epic("Epic 2")
        epics = await repo.get_all_epics()
        assert len(epics) == 2


class TestTaskCRUD:
    async def test_create_task(self, repo: Repository) -> None:
        epic = await repo.create_epic("Parent Epic")
        task = await repo.create_task(epic.id, "Test Task", "Description")
        assert task.title == "Test Task"
        assert task.epic_id == epic.id
        assert task.stage == TaskStage.PLANNING

    async def test_get_task(self, repo: Repository) -> None:
        epic = await repo.create_epic("Parent Epic")
        created = await repo.create_task(epic.id, "Test Task")
        fetched = await repo.get_task(created.id)
        assert fetched is not None
        assert fetched.title == "Test Task"

    async def test_update_task_stage(self, repo: Repository) -> None:
        epic = await repo.create_epic("Parent")
        task = await repo.create_task(epic.id, "Test Task")
        await repo.update_task_stage(task.id, TaskStage.IMPLEMENTING)
        updated = await repo.get_task(task.id)
        assert updated is not None
        assert updated.stage == TaskStage.IMPLEMENTING

    async def test_update_task_branch(self, repo: Repository) -> None:
        epic = await repo.create_epic("Parent")
        task = await repo.create_task(epic.id, "Test Task")
        await repo.update_task_branch(task.id, "task/abc-test", "/tmp/worktree")
        updated = await repo.get_task(task.id)
        assert updated is not None
        assert updated.branch_name == "task/abc-test"
        assert updated.worktree_path == "/tmp/worktree"

    async def test_increment_retry(self, repo: Repository) -> None:
        epic = await repo.create_epic("Parent")
        task = await repo.create_task(epic.id, "Test Task")
        count = await repo.increment_retry(task.id)
        assert count == 1
        count = await repo.increment_retry(task.id)
        assert count == 2

    async def test_get_tasks_by_epic(self, repo: Repository) -> None:
        epic = await repo.create_epic("Parent")
        await repo.create_task(epic.id, "Task 1")
        await repo.create_task(epic.id, "Task 2")
        tasks = await repo.get_tasks_by_epic(epic.id)
        assert len(tasks) == 2

    async def test_get_actionable_tasks(self, repo: Repository) -> None:
        epic = await repo.create_epic("Parent")
        t1 = await repo.create_task(epic.id, "Task 1")
        t2 = await repo.create_task(epic.id, "Task 2")
        await repo.update_task_stage(t2.id, TaskStage.MERGED)
        actionable = await repo.get_actionable_tasks()
        assert len(actionable) == 1
        assert actionable[0].id == t1.id


class TestArtifacts:
    async def test_create_and_get_artifact(self, repo: Repository) -> None:
        epic = await repo.create_epic("Parent")
        task = await repo.create_task(epic.id, "Task")
        artifact = await repo.create_artifact(
            kind="implementation_plan",
            content="# Plan\nDo the thing",
            task_id=task.id,
            epic_id=epic.id,
        )
        assert artifact.kind == "implementation_plan"

        artifacts = await repo.get_artifacts_for_task(task.id)
        assert len(artifacts) == 1

        artifacts = await repo.get_artifacts_for_task(task.id, kind="implementation_plan")
        assert len(artifacts) == 1

        artifacts = await repo.get_artifacts_for_task(task.id, kind="design_doc")
        assert len(artifacts) == 0


class TestContextAssembly:
    async def test_context_includes_epic(self, repo: Repository) -> None:
        epic = await repo.create_epic("My Epic", "Epic description")
        context = await repo.get_context_for_stage(epic_id=epic.id)
        assert "My Epic" in context
        assert "Epic description" in context

    async def test_context_includes_task_and_plan(self, repo: Repository) -> None:
        epic = await repo.create_epic("Parent")
        task = await repo.create_task(epic.id, "My Task", "Task desc")
        await repo.create_artifact(
            kind="implementation_plan", content="Step 1: do it",
            task_id=task.id, epic_id=epic.id,
        )
        context = await repo.get_context_for_stage(task_id=task.id)
        assert "My Task" in context
        assert "Step 1: do it" in context


class TestStageLog:
    async def test_stage_transition_logged(self, repo: Repository) -> None:
        epic = await repo.create_epic("Test")
        await repo.update_epic_stage(epic.id, EpicStage.DESIGNING, "Auto-advance")
        history = await repo.get_stage_history("epic", epic.id)
        assert len(history) == 1
        assert history[0].from_stage == EpicStage.BACKLOG
        assert history[0].to_stage == EpicStage.DESIGNING
        assert history[0].reason == "Auto-advance"


class TestEpicCompletion:
    async def test_epic_not_complete_with_pending_tasks(self, repo: Repository) -> None:
        epic = await repo.create_epic("Parent")
        await repo.create_task(epic.id, "Task 1")
        assert await repo.check_epic_complete(epic.id) is False

    async def test_epic_complete_when_all_ready(self, repo: Repository) -> None:
        epic = await repo.create_epic("Parent")
        t1 = await repo.create_task(epic.id, "Task 1")
        t2 = await repo.create_task(epic.id, "Task 2")
        await repo.update_task_stage(t1.id, TaskStage.READY_FOR_MASTER)
        await repo.update_task_stage(t2.id, TaskStage.MERGED)
        assert await repo.check_epic_complete(epic.id) is True

    async def test_epic_not_complete_with_no_tasks(self, repo: Repository) -> None:
        epic = await repo.create_epic("Empty")
        assert await repo.check_epic_complete(epic.id) is False
