"""TaskCard widget for the Kanban board."""

from __future__ import annotations

from textual.widget import Widget
from textual.reactive import reactive
from textual.message import Message
from textual.app import ComposeResult
from textual.widgets import Static


class TaskCard(Static):
    """A card representing a task or epic on the Kanban board."""

    DEFAULT_CSS = """
    TaskCard {
        width: 100%;
        height: auto;
        min-height: 3;
        margin: 0 0 1 0;
        padding: 0 1;
        background: $surface;
        border: solid $primary-background;
    }
    TaskCard:hover {
        background: $surface-lighten-1;
        border: solid $primary;
    }
    TaskCard.-selected {
        border: double $accent;
        background: $surface-lighten-2;
    }
    """

    class Selected(Message):
        """Emitted when a card is clicked."""
        def __init__(self, entity_type: str, entity_id: str) -> None:
            super().__init__()
            self.entity_type = entity_type
            self.entity_id = entity_id

    def __init__(
        self,
        entity_type: str,
        entity_id: str,
        title: str,
        subtitle: str = "",
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.title_text = title
        self.subtitle_text = subtitle

    def render(self) -> str:
        label = self.title_text[:18]
        if self.subtitle_text:
            return f"{label}\n[dim]{self.subtitle_text}[/dim]"
        return label

    def on_click(self) -> None:
        self.post_message(self.Selected(self.entity_type, self.entity_id))
