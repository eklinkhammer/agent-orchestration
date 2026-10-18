"""Tests for the pipeline state machine."""

from sovereign.pipeline.state_machine import (
    EpicStage,
    TaskStage,
    next_epic_stage,
    next_task_stage,
    retry_target,
    is_actionable_epic_stage,
    is_actionable_task_stage,
)


class TestEpicTransitions:
    def test_backlog_to_designing(self) -> None:
        assert next_epic_stage(EpicStage.BACKLOG) == EpicStage.DESIGNING

    def test_designing_to_decomposing(self) -> None:
        assert next_epic_stage(EpicStage.DESIGNING) == EpicStage.DECOMPOSING

    def test_decomposing_to_ready(self) -> None:
        assert next_epic_stage(EpicStage.DECOMPOSING) == EpicStage.READY_FOR_PLANNING

    def test_ready_is_terminal(self) -> None:
        assert next_epic_stage(EpicStage.READY_FOR_PLANNING) is None


class TestTaskTransitions:
    def test_happy_path(self) -> None:
        """Walk through the entire happy path."""
        stages = [
            TaskStage.PLANNING,
            TaskStage.IMPLEMENTING,
            TaskStage.VERIFYING,
            TaskStage.REVIEWING,
            TaskStage.MERGING_TO_DEV,
            TaskStage.UNIT_TESTING,
            TaskStage.INTEGRATION_TESTING,
            TaskStage.DOCKER_E2E_TESTING,
            TaskStage.READY_FOR_MASTER,
            TaskStage.MERGED,
        ]
        for i in range(len(stages) - 1):
            assert next_task_stage(stages[i]) == stages[i + 1], (
                f"Expected {stages[i]} -> {stages[i + 1]}"
            )

    def test_merged_is_terminal(self) -> None:
        assert next_task_stage(TaskStage.MERGED) is None

    def test_failed_is_terminal(self) -> None:
        assert next_task_stage(TaskStage.FAILED) is None


class TestRetryTargets:
    def test_verifying_retries_to_implementing(self) -> None:
        assert retry_target(TaskStage.VERIFYING) == TaskStage.IMPLEMENTING

    def test_reviewing_retries_to_implementing(self) -> None:
        assert retry_target(TaskStage.REVIEWING) == TaskStage.IMPLEMENTING

    def test_unit_testing_retries_to_implementing(self) -> None:
        assert retry_target(TaskStage.UNIT_TESTING) == TaskStage.IMPLEMENTING

    def test_integration_testing_retries_to_implementing(self) -> None:
        assert retry_target(TaskStage.INTEGRATION_TESTING) == TaskStage.IMPLEMENTING

    def test_docker_e2e_retries_to_implementing(self) -> None:
        assert retry_target(TaskStage.DOCKER_E2E_TESTING) == TaskStage.IMPLEMENTING

    def test_planning_no_retry(self) -> None:
        assert retry_target(TaskStage.PLANNING) is None

    def test_implementing_no_retry(self) -> None:
        assert retry_target(TaskStage.IMPLEMENTING) is None


class TestActionableStages:
    def test_designing_is_actionable(self) -> None:
        assert is_actionable_epic_stage(EpicStage.DESIGNING) is True

    def test_decomposing_is_actionable(self) -> None:
        assert is_actionable_epic_stage(EpicStage.DECOMPOSING) is True

    def test_backlog_not_actionable(self) -> None:
        assert is_actionable_epic_stage(EpicStage.BACKLOG) is False

    def test_all_task_work_stages_actionable(self) -> None:
        work_stages = [
            TaskStage.PLANNING, TaskStage.IMPLEMENTING,
            TaskStage.VERIFYING, TaskStage.REVIEWING,
            TaskStage.MERGING_TO_DEV, TaskStage.UNIT_TESTING,
            TaskStage.INTEGRATION_TESTING, TaskStage.DOCKER_E2E_TESTING,
        ]
        for stage in work_stages:
            assert is_actionable_task_stage(stage) is True, f"{stage} should be actionable"

    def test_ready_for_master_is_actionable(self) -> None:
        # READY_FOR_MASTER needs git merge to master
        assert is_actionable_task_stage(TaskStage.READY_FOR_MASTER) is True

    def test_terminal_stages_not_actionable(self) -> None:
        for stage in [TaskStage.MERGED, TaskStage.FAILED]:
            assert is_actionable_task_stage(stage) is False, f"{stage} should not be actionable"
