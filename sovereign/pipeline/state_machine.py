"""Stage enums and transition maps for epics and tasks."""

from __future__ import annotations

from enum import StrEnum


class EpicStage(StrEnum):
    BACKLOG = "backlog"
    DESIGNING = "designing"
    DECOMPOSING = "decomposing"
    READY_FOR_PLANNING = "ready_for_planning"


class TaskStage(StrEnum):
    PLANNING = "planning"
    IMPLEMENTING = "implementing"
    VERIFYING = "verifying"
    REVIEWING = "reviewing"
    MERGING_TO_DEV = "merging_to_dev"
    UNIT_TESTING = "unit_testing"
    INTEGRATION_TESTING = "integration_testing"
    DOCKER_E2E_TESTING = "docker_e2e_testing"
    READY_FOR_MASTER = "ready_for_master"
    MERGED = "merged"
    FAILED = "failed"


# ── Forward transitions (happy path) ──

EPIC_TRANSITIONS: dict[EpicStage, EpicStage | None] = {
    EpicStage.BACKLOG: EpicStage.DESIGNING,
    EpicStage.DESIGNING: EpicStage.DECOMPOSING,
    EpicStage.DECOMPOSING: EpicStage.READY_FOR_PLANNING,
    EpicStage.READY_FOR_PLANNING: None,  # terminal
}

TASK_TRANSITIONS: dict[TaskStage, TaskStage | None] = {
    TaskStage.PLANNING: TaskStage.IMPLEMENTING,
    TaskStage.IMPLEMENTING: TaskStage.VERIFYING,
    TaskStage.VERIFYING: TaskStage.REVIEWING,
    TaskStage.REVIEWING: TaskStage.MERGING_TO_DEV,
    TaskStage.MERGING_TO_DEV: TaskStage.UNIT_TESTING,
    TaskStage.UNIT_TESTING: TaskStage.INTEGRATION_TESTING,
    TaskStage.INTEGRATION_TESTING: TaskStage.DOCKER_E2E_TESTING,
    TaskStage.DOCKER_E2E_TESTING: TaskStage.READY_FOR_MASTER,
    TaskStage.READY_FOR_MASTER: TaskStage.MERGED,
    TaskStage.MERGED: None,  # terminal
    TaskStage.FAILED: None,  # terminal
}

# ── Retry transitions (failure paths) ──
# When verification/review/CI fails, task goes back to implementing
TASK_RETRY_TARGETS: dict[TaskStage, TaskStage] = {
    TaskStage.VERIFYING: TaskStage.IMPLEMENTING,
    TaskStage.REVIEWING: TaskStage.IMPLEMENTING,
    TaskStage.UNIT_TESTING: TaskStage.IMPLEMENTING,
    TaskStage.INTEGRATION_TESTING: TaskStage.IMPLEMENTING,
    TaskStage.DOCKER_E2E_TESTING: TaskStage.IMPLEMENTING,
}

# ── Agent role mapping ──
EPIC_STAGE_ROLES: dict[EpicStage, str] = {
    EpicStage.DESIGNING: "architect",
    EpicStage.DECOMPOSING: "decomposer",
}

TASK_STAGE_ROLES: dict[TaskStage, str] = {
    TaskStage.PLANNING: "planner",
    TaskStage.IMPLEMENTING: "implementer",
    TaskStage.VERIFYING: "verifier",
    TaskStage.REVIEWING: "reviewer",
}

# Stages that need test runners instead of Claude agents
TASK_CI_STAGES: set[TaskStage] = {
    TaskStage.UNIT_TESTING,
    TaskStage.INTEGRATION_TESTING,
    TaskStage.DOCKER_E2E_TESTING,
}

# Stages that need git operations
TASK_GIT_STAGES: set[TaskStage] = {
    TaskStage.MERGING_TO_DEV,
    TaskStage.READY_FOR_MASTER,
}


def next_epic_stage(current: EpicStage) -> EpicStage | None:
    """Return the next epic stage, or None if terminal."""
    return EPIC_TRANSITIONS.get(current)


def next_task_stage(current: TaskStage) -> TaskStage | None:
    """Return the next task stage, or None if terminal."""
    return TASK_TRANSITIONS.get(current)


def retry_target(current: TaskStage) -> TaskStage | None:
    """Return the stage to retry from, or None if retries not applicable."""
    return TASK_RETRY_TARGETS.get(current)


def is_actionable_epic_stage(stage: EpicStage) -> bool:
    """True if this epic stage requires an agent to run."""
    return stage in EPIC_STAGE_ROLES


def is_actionable_task_stage(stage: TaskStage) -> bool:
    """True if this task stage requires work (agent, CI, or git)."""
    return stage in TASK_STAGE_ROLES or stage in TASK_CI_STAGES or stage in TASK_GIT_STAGES
