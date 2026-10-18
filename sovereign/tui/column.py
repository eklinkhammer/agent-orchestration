"""StageColumn widget — a vertical list of cards for one pipeline stage."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from sovereign.tui.card import TaskCard


class StageColumn(Vertical):
    """A column in the Kanban board representing one stage."""

    DEFAULT_CSS = """
    StageColumn {
        width: 1fr;
        height: 100%;
        min-width: 12;
        max-width: 24;
        border-right: solid $primary-background-darken-2;
        padding: 0;
    }
    StageColumn > .column-header {
        width: 100%;
        height: 1;
        text-align: center;
        text-style: bold;
        background: $primary-background;
        color: $text;
    }
    StageColumn > .column-body {
        width: 100%;
        height: 1fr;
        overflow-y: auto;
        padding: 1 0;
    }
    """

    def __init__(self, stage_name: str, display_name: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.stage_name = stage_name
        self.display_name = display_name

    def compose(self) -> ComposeResult:
        yield Static(self.display_name, classes="column-header")
        yield Vertical(id=f"col-body-{self.stage_name}", classes="column-body")

    def set_cards(self, cards: list[TaskCard]) -> None:
        """Replace all cards in this column."""
        body = self.query_one(f"#col-body-{self.stage_name}", Vertical)
        body.remove_children()
        for card in cards:
            body.mount(card)
