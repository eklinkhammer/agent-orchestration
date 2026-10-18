"""Dataclass models for database rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Epic:
    id: str
    title: str
    description: str = ""
    stage: str = "backlog"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Task:
    id: str
    epic_id: str
    title: str
    description: str = ""
    stage: str = "planning"
    branch_name: str | None = None
    worktree_path: str | None = None
    retry_count: int = 0
    dependencies: str = "[]"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class AgentRun:
    id: str
    role: str
    stage: str
    prompt: str
    task_id: str | None = None
    epic_id: str | None = None
    output: str | None = None
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_sec: float | None = None
    session_id: str | None = None
    status: str = "running"
    started_at: str = ""
    finished_at: str | None = None


@dataclass
class Artifact:
    id: str
    kind: str
    content: str
    task_id: str | None = None
    epic_id: str | None = None
    run_id: str | None = None
    created_at: str = ""


@dataclass
class StageLogEntry:
    entity_type: str
    entity_id: str
    to_stage: str
    from_stage: str | None = None
    reason: str | None = None
    id: int | None = None
    created_at: str = ""
