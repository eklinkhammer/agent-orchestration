"""Detail panel — shows info about the selected card."""

from __future__ import annotations

from textual.widgets import Static

from sovereign.db.models import Epic, Task


class DetailView(Static):
    """Bottom panel showing details of the selected entity."""

    DEFAULT_CSS = """
    DetailView {
        width: 100%;
        height: auto;
        min-height: 4;
        max-height: 8;
        padding: 0 1;
        background: $surface;
        border-top: solid $primary-background;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._content = "Select a card to view details"

    def show_epic(self, epic: Epic) -> None:
        self._content = (
            f"[bold]Epic:[/bold] {epic.title} | "
            f"[bold]Stage:[/bold] {epic.stage} | "
            f"[bold]ID:[/bold] {epic.id}"
        )
        if epic.description:
            self._content += f"\n{epic.description[:200]}"
        self.update(self._content)

    def show_task(self, task: Task, agent_status: str = "", cost: float = 0.0) -> None:
        self._content = (
            f"[bold]Task:[/bold] {task.title} | "
            f"[bold]Stage:[/bold] {task.stage} | "
            f"[bold]Retries:[/bold] {task.retry_count}/3"
        )
        if task.branch_name:
            self._content += f"\n[bold]Branch:[/bold] {task.branch_name}"
        if agent_status:
            self._content += f" | [bold]Agent:[/bold] {agent_status}"
        if cost > 0:
            self._content += f" | [bold]Cost:[/bold] ${cost:.2f}"
        self.update(self._content)

    def clear_detail(self) -> None:
        self._content = "Select a card to view details"
        self.update(self._content)
