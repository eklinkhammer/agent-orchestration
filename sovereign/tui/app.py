"""Main Textual application for the Sovereign pipeline TUI."""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, Static
from textual.screen import ModalScreen

from sovereign.config import Config
from sovereign.db.repository import Repository
from sovereign.pipeline.orchestrator import Orchestrator
from sovereign.tui.card import TaskCard
from sovereign.tui.detail_view import DetailView
from sovereign.tui.kanban import KanbanBoard


class NewEpicScreen(ModalScreen[str | None]):
    """Modal screen for creating a new epic."""

    DEFAULT_CSS = """
    NewEpicScreen {
        align: center middle;
    }
    NewEpicScreen > Vertical {
        width: 60;
        height: auto;
        max-height: 20;
        background: $surface;
        border: double $primary;
        padding: 1 2;
    }
    NewEpicScreen > Vertical > Static {
        width: 100%;
        margin-bottom: 1;
    }
    NewEpicScreen > Vertical > Input {
        width: 100%;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[bold]New Epic[/bold]")
            yield Input(placeholder="Epic title...", id="epic-title")
            yield Input(placeholder="Description (optional)...", id="epic-desc")
            yield Static("[dim]Enter to create, Escape to cancel[/dim]")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "epic-title":
            title_input = self.query_one("#epic-title", Input)
            title = title_input.value.strip()
            if title:
                self.dismiss(title)
            else:
                self.dismiss(None)
        elif event.input.id == "epic-desc":
            title_input = self.query_one("#epic-title", Input)
            title = title_input.value.strip()
            if title:
                self.dismiss(title)
            else:
                self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SovereignApp(App[None]):
    """Sovereign Tech Pipeline — Kanban TUI."""

    TITLE = "Sovereign Tech Pipeline"
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("n", "new_epic", "New Epic"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(
        self,
        config: Config,
        repo: Repository,
        orchestrator: Orchestrator,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.config = config
        self.repo = repo
        self.orchestrator = orchestrator
        self._refresh_timer: asyncio.TimerHandle | None = None
        self._orchestrator_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield KanbanBoard()
        yield DetailView(id="detail")
        yield Footer()

    async def on_mount(self) -> None:
        """Start the orchestrator and periodic refresh."""
        # Start orchestrator in background
        self._orchestrator_task = asyncio.create_task(self.orchestrator.start())
        # Start periodic refresh
        self.set_interval(self.config.tui_refresh_interval, self._refresh_board)

    async def _refresh_board(self) -> None:
        """Poll the database and update the Kanban board."""
        try:
            epics = await self.repo.get_all_epics()
            tasks = await self.repo.get_all_tasks()
            board = self.query_one(KanbanBoard)
            board.update_board(epics, tasks)
        except Exception:
            pass  # Silently handle refresh errors

    def on_task_card_selected(self, message: TaskCard.Selected) -> None:
        """Handle card selection — show details in bottom panel."""
        asyncio.create_task(self._show_detail(message.entity_type, message.entity_id))

    async def _show_detail(self, entity_type: str, entity_id: str) -> None:
        """Load and display details for a selected entity."""
        detail = self.query_one("#detail", DetailView)
        if entity_type == "epic":
            epic = await self.repo.get_epic(entity_id)
            if epic:
                detail.show_epic(epic)
        elif entity_type == "task":
            task = await self.repo.get_task(entity_id)
            if task:
                cost = await self.repo.get_total_cost()
                detail.show_task(task, cost=cost)

    def action_new_epic(self) -> None:
        """Show the new epic modal."""
        self.push_screen(NewEpicScreen(), callback=self._on_new_epic_dismissed)

    async def _on_new_epic_dismissed(self, title: str | None) -> None:
        """Handle the result of the new epic modal."""
        if title:
            await self.repo.create_epic(title)
            await self._refresh_board()

    async def action_refresh(self) -> None:
        """Manual refresh."""
        await self._refresh_board()

    async def on_unmount(self) -> None:
        """Clean up on exit."""
        await self.orchestrator.stop()
        if self._orchestrator_task:
            self._orchestrator_task.cancel()
            try:
                await self._orchestrator_task
            except asyncio.CancelledError:
                pass
