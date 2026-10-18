"""Async repository for all database CRUD operations and context assembly."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from sovereign.db.models import Artifact, AgentRun, Epic, StageLogEntry, Task
from sovereign.pipeline.state_machine import EpicStage, TaskStage


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    """All database operations for the sovereign pipeline."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    # ── Epics ──

    async def create_epic(self, title: str, description: str = "") -> Epic:
        epic = Epic(id=_new_id(), title=title, description=description,
                    stage=EpicStage.BACKLOG, created_at=_now(), updated_at=_now())
        await self.db.execute(
            "INSERT INTO epics (id, title, description, stage, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (epic.id, epic.title, epic.description, epic.stage, epic.created_at, epic.updated_at),
        )
        await self.db.commit()
        return epic

    async def get_epic(self, epic_id: str) -> Epic | None:
        async with self.db.execute("SELECT * FROM epics WHERE id = ?", (epic_id,)) as cur:
            row = await cur.fetchone()
            return Epic(**dict(row)) if row else None

    async def get_epics_by_stage(self, stage: str) -> list[Epic]:
        async with self.db.execute(
            "SELECT * FROM epics WHERE stage = ? ORDER BY created_at", (stage,)
        ) as cur:
            return [Epic(**dict(row)) async for row in cur]

    async def get_all_epics(self) -> list[Epic]:
        async with self.db.execute("SELECT * FROM epics ORDER BY created_at") as cur:
            return [Epic(**dict(row)) async for row in cur]

    async def update_epic_stage(
        self, epic_id: str, new_stage: str, reason: str | None = None
    ) -> None:
        epic = await self.get_epic(epic_id)
        if not epic:
            return
        old_stage = epic.stage
        now = _now()
        await self.db.execute(
            "UPDATE epics SET stage = ?, updated_at = ? WHERE id = ?",
            (new_stage, now, epic_id),
        )
        await self._log_transition("epic", epic_id, old_stage, new_stage, reason)
        await self.db.commit()

    # ── Tasks ──

    async def create_task(
        self,
        epic_id: str,
        title: str,
        description: str = "",
        dependencies: list[str] | None = None,
    ) -> Task:
        task = Task(
            id=_new_id(),
            epic_id=epic_id,
            title=title,
            description=description,
            stage=TaskStage.PLANNING,
            dependencies=json.dumps(dependencies or []),
            created_at=_now(),
            updated_at=_now(),
        )
        await self.db.execute(
            "INSERT INTO tasks (id, epic_id, title, description, stage, dependencies, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task.id, task.epic_id, task.title, task.description, task.stage,
             task.dependencies, task.created_at, task.updated_at),
        )
        await self.db.commit()
        return task

    async def get_task(self, task_id: str) -> Task | None:
        async with self.db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
            row = await cur.fetchone()
            return Task(**dict(row)) if row else None

    async def get_tasks_by_epic(self, epic_id: str) -> list[Task]:
        async with self.db.execute(
            "SELECT * FROM tasks WHERE epic_id = ? ORDER BY created_at", (epic_id,)
        ) as cur:
            return [Task(**dict(row)) async for row in cur]

    async def get_tasks_by_stage(self, stage: str) -> list[Task]:
        async with self.db.execute(
            "SELECT * FROM tasks WHERE stage = ? ORDER BY created_at", (stage,)
        ) as cur:
            return [Task(**dict(row)) async for row in cur]

    async def get_all_tasks(self) -> list[Task]:
        async with self.db.execute("SELECT * FROM tasks ORDER BY created_at") as cur:
            return [Task(**dict(row)) async for row in cur]

    async def update_task_stage(
        self, task_id: str, new_stage: str, reason: str | None = None
    ) -> None:
        task = await self.get_task(task_id)
        if not task:
            return
        old_stage = task.stage
        now = _now()
        await self.db.execute(
            "UPDATE tasks SET stage = ?, updated_at = ? WHERE id = ?",
            (new_stage, now, task_id),
        )
        await self._log_transition("task", task_id, old_stage, new_stage, reason)
        await self.db.commit()

    async def update_task_branch(
        self, task_id: str, branch_name: str, worktree_path: str
    ) -> None:
        await self.db.execute(
            "UPDATE tasks SET branch_name = ?, worktree_path = ?, updated_at = ? WHERE id = ?",
            (branch_name, worktree_path, _now(), task_id),
        )
        await self.db.commit()

    async def increment_retry(self, task_id: str) -> int:
        await self.db.execute(
            "UPDATE tasks SET retry_count = retry_count + 1, updated_at = ? WHERE id = ?",
            (_now(), task_id),
        )
        await self.db.commit()
        task = await self.get_task(task_id)
        return task.retry_count if task else 0

    # ── Agent runs ──

    async def create_agent_run(
        self,
        role: str,
        stage: str,
        prompt: str,
        task_id: str | None = None,
        epic_id: str | None = None,
    ) -> AgentRun:
        run = AgentRun(
            id=_new_id(), role=role, stage=stage, prompt=prompt,
            task_id=task_id, epic_id=epic_id, started_at=_now(),
        )
        await self.db.execute(
            "INSERT INTO agent_runs (id, task_id, epic_id, role, stage, prompt, status, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run.id, run.task_id, run.epic_id, run.role, run.stage, run.prompt,
             run.status, run.started_at),
        )
        await self.db.commit()
        return run

    async def finish_agent_run(
        self,
        run_id: str,
        output: str,
        status: str = "completed",
        cost_usd: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        duration_sec: float | None = None,
        session_id: str | None = None,
    ) -> None:
        await self.db.execute(
            "UPDATE agent_runs SET output = ?, status = ?, cost_usd = ?, "
            "input_tokens = ?, output_tokens = ?, duration_sec = ?, "
            "session_id = ?, finished_at = ? WHERE id = ?",
            (output, status, cost_usd, input_tokens, output_tokens,
             duration_sec, session_id, _now(), run_id),
        )
        await self.db.commit()

    async def get_runs_for_task(self, task_id: str) -> list[AgentRun]:
        async with self.db.execute(
            "SELECT * FROM agent_runs WHERE task_id = ? ORDER BY started_at", (task_id,)
        ) as cur:
            return [AgentRun(**dict(row)) async for row in cur]

    async def get_runs_for_epic(self, epic_id: str) -> list[AgentRun]:
        async with self.db.execute(
            "SELECT * FROM agent_runs WHERE epic_id = ? ORDER BY started_at", (epic_id,)
        ) as cur:
            return [AgentRun(**dict(row)) async for row in cur]

    # ── Artifacts ──

    async def create_artifact(
        self,
        kind: str,
        content: str,
        task_id: str | None = None,
        epic_id: str | None = None,
        run_id: str | None = None,
    ) -> Artifact:
        artifact = Artifact(
            id=_new_id(), kind=kind, content=content,
            task_id=task_id, epic_id=epic_id, run_id=run_id, created_at=_now(),
        )
        await self.db.execute(
            "INSERT INTO artifacts (id, task_id, epic_id, run_id, kind, content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (artifact.id, artifact.task_id, artifact.epic_id, artifact.run_id,
             artifact.kind, artifact.content, artifact.created_at),
        )
        await self.db.commit()
        return artifact

    async def get_artifacts_for_task(self, task_id: str, kind: str | None = None) -> list[Artifact]:
        if kind:
            query = "SELECT * FROM artifacts WHERE task_id = ? AND kind = ? ORDER BY created_at"
            params = (task_id, kind)
        else:
            query = "SELECT * FROM artifacts WHERE task_id = ? ORDER BY created_at"
            params = (task_id,)
        async with self.db.execute(query, params) as cur:
            return [Artifact(**dict(row)) async for row in cur]

    async def get_artifacts_for_epic(self, epic_id: str, kind: str | None = None) -> list[Artifact]:
        if kind:
            query = "SELECT * FROM artifacts WHERE epic_id = ? AND kind = ? ORDER BY created_at"
            params = (epic_id, kind)
        else:
            query = "SELECT * FROM artifacts WHERE epic_id = ? ORDER BY created_at"
            params = (epic_id,)
        async with self.db.execute(query, params) as cur:
            return [Artifact(**dict(row)) async for row in cur]

    # ── Context assembly ──

    async def get_context_for_stage(
        self, task_id: str | None = None, epic_id: str | None = None
    ) -> str:
        """Assemble relevant context from prior artifacts for the current stage."""
        parts: list[str] = []

        if epic_id:
            epic = await self.get_epic(epic_id)
            if epic:
                parts.append(f"# Epic: {epic.title}\n{epic.description}")

            # Include design doc if it exists
            design_docs = await self.get_artifacts_for_epic(epic_id, "design_doc")
            if design_docs:
                parts.append(f"## Design Document\n{design_docs[-1].content}")

        if task_id:
            task = await self.get_task(task_id)
            if task:
                parts.append(f"# Task: {task.title}\n{task.description}")

                # Include epic context
                if not epic_id:
                    epic = await self.get_epic(task.epic_id)
                    if epic:
                        parts.append(f"## Parent Epic: {epic.title}\n{epic.description}")

                # Include implementation plan
                plans = await self.get_artifacts_for_task(task_id, "implementation_plan")
                if plans:
                    parts.append(f"## Implementation Plan\n{plans[-1].content}")

                # Include latest code diff
                diffs = await self.get_artifacts_for_task(task_id, "code_diff")
                if diffs:
                    parts.append(f"## Latest Code Diff\n{diffs[-1].content}")

                # Include verification reports (useful for retry context)
                verifications = await self.get_artifacts_for_task(task_id, "verification_report")
                if verifications:
                    parts.append(f"## Verification Report\n{verifications[-1].content}")

                # Include review reports (useful for retry context)
                reviews = await self.get_artifacts_for_task(task_id, "review_report")
                if reviews:
                    parts.append(f"## Review Report\n{reviews[-1].content}")

                # Include test results (useful for CI retry context)
                test_results = await self.get_artifacts_for_task(task_id, "test_result")
                if test_results:
                    parts.append(f"## Latest Test Results\n{test_results[-1].content}")

        return "\n\n---\n\n".join(parts)

    async def get_actionable_epics(self) -> list[Epic]:
        """Get epics that need agent work (designing or decomposing)."""
        async with self.db.execute(
            "SELECT * FROM epics WHERE stage IN ('backlog', 'designing', 'decomposing') "
            "ORDER BY created_at"
        ) as cur:
            return [Epic(**dict(row)) async for row in cur]

    async def get_actionable_tasks(self) -> list[Task]:
        """Get tasks that need work (not in terminal or waiting states)."""
        actionable_stages = (
            TaskStage.PLANNING, TaskStage.IMPLEMENTING, TaskStage.VERIFYING,
            TaskStage.REVIEWING, TaskStage.MERGING_TO_DEV, TaskStage.UNIT_TESTING,
            TaskStage.INTEGRATION_TESTING, TaskStage.DOCKER_E2E_TESTING,
        )
        placeholders = ",".join("?" for _ in actionable_stages)
        async with self.db.execute(
            f"SELECT * FROM tasks WHERE stage IN ({placeholders}) ORDER BY created_at",
            actionable_stages,
        ) as cur:
            return [Task(**dict(row)) async for row in cur]

    async def check_epic_complete(self, epic_id: str) -> bool:
        """Check if all tasks for an epic are ready_for_master or merged."""
        tasks = await self.get_tasks_by_epic(epic_id)
        if not tasks:
            return False
        return all(t.stage in (TaskStage.READY_FOR_MASTER, TaskStage.MERGED) for t in tasks)

    # ── Stage log ──

    async def _log_transition(
        self,
        entity_type: str,
        entity_id: str,
        from_stage: str | None,
        to_stage: str,
        reason: str | None = None,
    ) -> None:
        await self.db.execute(
            "INSERT INTO stage_log (entity_type, entity_id, from_stage, to_stage, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (entity_type, entity_id, from_stage, to_stage, reason),
        )

    async def get_stage_history(self, entity_type: str, entity_id: str) -> list[StageLogEntry]:
        async with self.db.execute(
            "SELECT * FROM stage_log WHERE entity_type = ? AND entity_id = ? ORDER BY created_at",
            (entity_type, entity_id),
        ) as cur:
            return [StageLogEntry(**dict(row)) async for row in cur]

    # ── Stats ──

    async def get_total_cost(self) -> float:
        async with self.db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) as total FROM agent_runs"
        ) as cur:
            row = await cur.fetchone()
            return float(row["total"]) if row else 0.0

    async def get_running_agents_count(self) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) as cnt FROM agent_runs WHERE status = 'running'"
        ) as cur:
            row = await cur.fetchone()
            return int(row["cnt"]) if row else 0
