"""KanbanBoard — horizontal layout of stage columns."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget

from sovereign.db.models import Epic, Task
from sovereign.pipeline.state_machine import EpicStage, TaskStage
from sovereign.tui.card import TaskCard
from sovereign.tui.column import StageColumn

# All stages to display as columns, in order
COLUMN_DEFS: list[tuple[str, str]] = [
    ("backlog", "Backlog"),
    ("designing", "Design"),
    ("decomposing", "Decomp"),
    ("planning", "Plan"),
    ("implementing", "Impl"),
    ("verifying", "Verify"),
    ("reviewing", "Review"),
    ("merging_to_dev", "→Dev"),
    ("unit_testing", "UTest"),
    ("integration_testing", "ITest"),
    ("docker_e2e_testing", "E2E"),
    ("ready_for_master", "Ready"),
]


class KanbanBoard(Horizontal):
    """Horizontal Kanban board with stage columns."""

    DEFAULT_CSS = """
    KanbanBoard {
        width: 100%;
        height: 1fr;
        overflow-x: auto;
    }
    """

    def compose(self) -> ComposeResult:
        for stage_name, display_name in COLUMN_DEFS:
            yield StageColumn(stage_name, display_name, id=f"stage-{stage_name}")

    def update_board(self, epics: list[Epic], tasks: list[Task]) -> None:
        """Rebuild all column contents from current data."""
        # Group items by stage
        stage_cards: dict[str, list[TaskCard]] = {s: [] for s, _ in COLUMN_DEFS}

        # Epic stages map to kanban columns
        for epic in epics:
            if epic.stage in stage_cards:
                stage_cards[epic.stage].append(
                    TaskCard(
                        entity_type="epic",
                        entity_id=epic.id,
                        title=epic.title,
                        subtitle=f"Epic",
                    )
                )

        # Task stages map directly
        for task in tasks:
            if task.stage in stage_cards:
                retry_info = f" R{task.retry_count}" if task.retry_count > 0 else ""
                stage_cards[task.stage].append(
                    TaskCard(
                        entity_type="task",
                        entity_id=task.id,
                        title=task.title,
                        subtitle=f"Task{retry_info}",
                    )
                )

        # Update each column
        for stage_name, _ in COLUMN_DEFS:
            try:
                col = self.query_one(f"#stage-{stage_name}", StageColumn)
                col.set_cards(stage_cards.get(stage_name, []))
            except Exception:
                pass
