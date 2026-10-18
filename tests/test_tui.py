"""Tests for the Textual TUI — board rendering, key bindings, card interaction."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from textual.widgets import Input

from sovereign.config import Config
from sovereign.db.schema import init_db
from sovereign.db.repository import Repository
from sovereign.pipeline.state_machine import EpicStage, TaskStage
from sovereign.pipeline.orchestrator import Orchestrator
from sovereign.pipeline.git_manager import GitManager
from sovereign.agents.base import AgentRunner
from sovereign.testing.runner import TestRunner as CITestRunner
from sovereign.tui.app import SovereignApp, NewEpicScreen
from sovereign.tui.kanban import KanbanBoard, COLUMN_DEFS
from sovereign.tui.column import StageColumn
from sovereign.tui.card import TaskCard
from sovereign.tui.detail_view import DetailView


# ── Test-friendly app that skips the orchestrator ──


class TestableApp(SovereignApp):
    """App subclass that doesn't start the orchestrator on mount."""

    CSS_PATH = Path(__file__).parent.parent / "sovereign" / "tui" / "styles.tcss"

    async def on_mount(self) -> None:
        await self._refresh_board()


# ── Fixtures ──


@pytest.fixture
async def app_env(tmp_path):
    """Provide (app, repo) with an initialized DB and no orchestrator."""
    config = Config(
        db_path=tmp_path / "test.db",
        project_root=tmp_path,
        worktree_dir=tmp_path / "worktrees",
        prompts_dir=tmp_path / "prompts",
    )
    config.ensure_dirs()
    db = await init_db(str(config.db_path))
    repo = Repository(db)

    git = MagicMock(spec=GitManager)
    git.ensure_branches = AsyncMock()
    runner = MagicMock(spec=AgentRunner)
    test_runner = MagicMock(spec=CITestRunner)
    orchestrator = Orchestrator(config, repo, git, runner, test_runner)

    app = TestableApp(config=config, repo=repo, orchestrator=orchestrator)
    yield app, repo
    await db.close()


# ── Layout & rendering ──


class TestBoardLayout:
    async def test_app_has_kanban_board(self, app_env) -> None:
        app, _ = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            boards = app.query(KanbanBoard)
            assert len(boards) == 1

    async def test_all_twelve_columns_exist(self, app_env) -> None:
        app, _ = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            for stage_name, _ in COLUMN_DEFS:
                col = app.query_one(f"#stage-{stage_name}", StageColumn)
                assert col.stage_name == stage_name

    async def test_column_headers_match_display_names(self, app_env) -> None:
        app, _ = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            for stage_name, display_name in COLUMN_DEFS:
                col = app.query_one(f"#stage-{stage_name}", StageColumn)
                assert col.display_name == display_name

    async def test_detail_panel_exists(self, app_env) -> None:
        app, _ = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            detail = app.query_one("#detail", DetailView)
            assert detail is not None

    async def test_header_and_footer_present(self, app_env) -> None:
        app, _ = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            from textual.widgets import Header, Footer

            assert len(app.query(Header)) == 1
            assert len(app.query(Footer)) == 1


# ── Board data rendering ──


class TestBoardData:
    async def test_epic_appears_in_backlog(self, app_env) -> None:
        app, repo = app_env
        await repo.create_epic("Auth feature", "Add OAuth")

        async with app.run_test(size=(160, 30)) as pilot:
            await app._refresh_board()
            await pilot.pause()

            cards = app.query(TaskCard)
            backlog_cards = [c for c in cards if c.entity_type == "epic"]
            assert len(backlog_cards) == 1
            assert backlog_cards[0].title_text == "Auth feature"

    async def test_epic_in_designing_column(self, app_env) -> None:
        app, repo = app_env
        epic = await repo.create_epic("Payment system")
        await repo.update_epic_stage(epic.id, EpicStage.DESIGNING)

        async with app.run_test(size=(160, 30)) as pilot:
            await app._refresh_board()
            await pilot.pause()

            cards = app.query(TaskCard)
            assert any(c.title_text == "Payment system" for c in cards)

    async def test_tasks_appear_in_correct_columns(self, app_env) -> None:
        app, repo = app_env
        epic = await repo.create_epic("Search")
        await repo.update_epic_stage(epic.id, EpicStage.READY_FOR_PLANNING)

        t1 = await repo.create_task(epic.id, "Task A")
        t2 = await repo.create_task(epic.id, "Task B")
        await repo.update_task_stage(t2.id, TaskStage.IMPLEMENTING)
        t3 = await repo.create_task(epic.id, "Task C")
        await repo.update_task_stage(t3.id, TaskStage.REVIEWING)

        async with app.run_test(size=(160, 30)) as pilot:
            await app._refresh_board()
            await pilot.pause()

            cards = app.query(TaskCard)
            task_cards = {c.title_text: c for c in cards if c.entity_type == "task"}
            assert "Task A" in task_cards
            assert "Task B" in task_cards
            assert "Task C" in task_cards

    async def test_retry_count_shown_in_subtitle(self, app_env) -> None:
        app, repo = app_env
        epic = await repo.create_epic("Epic")
        task = await repo.create_task(epic.id, "Retry task")
        await repo.update_task_stage(task.id, TaskStage.IMPLEMENTING)
        await repo.increment_retry(task.id)
        await repo.increment_retry(task.id)

        async with app.run_test(size=(160, 30)) as pilot:
            await app._refresh_board()
            await pilot.pause()

            cards = app.query(TaskCard)
            retry_card = next(c for c in cards if c.title_text == "Retry task")
            assert "R2" in retry_card.subtitle_text

    async def test_empty_board_has_no_cards(self, app_env) -> None:
        app, _ = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            cards = app.query(TaskCard)
            assert len(cards) == 0

    async def test_multiple_epics_across_stages(self, app_env) -> None:
        app, repo = app_env
        e1 = await repo.create_epic("Epic 1")
        e2 = await repo.create_epic("Epic 2")
        await repo.update_epic_stage(e2.id, EpicStage.DESIGNING)
        e3 = await repo.create_epic("Epic 3")
        await repo.update_epic_stage(e3.id, EpicStage.DECOMPOSING)

        async with app.run_test(size=(160, 30)) as pilot:
            await app._refresh_board()
            await pilot.pause()

            cards = app.query(TaskCard)
            epic_cards = [c for c in cards if c.entity_type == "epic"]
            assert len(epic_cards) == 3

    async def test_refresh_picks_up_new_data(self, app_env) -> None:
        app, repo = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            assert len(app.query(TaskCard)) == 0

            await repo.create_epic("Late addition")
            await app._refresh_board()
            await pilot.pause()

            cards = app.query(TaskCard)
            assert any(c.title_text == "Late addition" for c in cards)


# ── Key bindings ──


class TestKeyBindings:
    async def test_n_opens_new_epic_modal(self, app_env) -> None:
        app, _ = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            await pilot.press("n")
            await pilot.pause()

            # Modal screen should be on top
            assert isinstance(app.screen, NewEpicScreen)

            # Dismiss the modal so shutdown doesn't hang
            await pilot.press("escape")
            await pilot.pause()

    async def test_escape_dismisses_modal(self, app_env) -> None:
        app, _ = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            await pilot.press("n")
            await pilot.pause()
            assert isinstance(app.screen, NewEpicScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, NewEpicScreen)

    async def test_r_triggers_refresh(self, app_env) -> None:
        app, repo = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            await repo.create_epic("Refresh target")
            await pilot.press("r")
            await pilot.pause()

            cards = app.query(TaskCard)
            assert any(c.title_text == "Refresh target" for c in cards)


# ── New epic modal ──


class TestNewEpicModal:
    async def test_modal_has_title_input(self, app_env) -> None:
        app, _ = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            await pilot.press("n")
            await pilot.pause()

            title_input = app.screen.query_one("#epic-title", Input)
            assert title_input is not None
            assert title_input.placeholder == "Epic title..."

            await pilot.press("escape")
            await pilot.pause()

    async def test_modal_has_description_input(self, app_env) -> None:
        app, _ = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            await pilot.press("n")
            await pilot.pause()

            desc_input = app.screen.query_one("#epic-desc", Input)
            assert desc_input is not None
            assert desc_input.placeholder == "Description (optional)..."

            await pilot.press("escape")
            await pilot.pause()

    async def test_submit_creates_epic(self, app_env) -> None:
        app, repo = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            await pilot.press("n")
            await pilot.pause()

            # Type a title and submit via Enter key
            title_input = app.screen.query_one("#epic-title", Input)
            title_input.value = "New feature"
            await title_input.action_submit()
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            epics = await repo.get_all_epics()
            assert len(epics) == 1
            assert epics[0].title == "New feature"
            assert epics[0].stage == EpicStage.BACKLOG

    async def test_empty_title_does_not_create_epic(self, app_env) -> None:
        app, repo = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            await pilot.press("n")
            await pilot.pause()

            # Submit empty — should dismiss without creating
            title_input = app.screen.query_one("#epic-title", Input)
            title_input.value = ""
            await title_input.action_submit()
            await pilot.pause()
            await pilot.pause()

            epics = await repo.get_all_epics()
            assert len(epics) == 0


# ── Detail panel ──


class TestDetailPanel:
    async def test_detail_shows_default_text(self, app_env) -> None:
        app, _ = app_env
        async with app.run_test(size=(160, 30)) as pilot:
            detail = app.query_one("#detail", DetailView)
            assert detail._content == "Select a card to view details"

    async def test_show_epic_detail(self, app_env) -> None:
        app, repo = app_env
        epic = await repo.create_epic("Test Epic", "Some description")
        async with app.run_test(size=(160, 30)) as pilot:
            detail = app.query_one("#detail", DetailView)
            detail.show_epic(epic)
            assert "Test Epic" in detail._content
            assert epic.stage in detail._content
            assert "Some description" in detail._content

    async def test_show_task_detail(self, app_env) -> None:
        app, repo = app_env
        epic = await repo.create_epic("Parent")
        task = await repo.create_task(epic.id, "My Task")
        task.branch_name = "task/abc-my-task"

        async with app.run_test(size=(160, 30)) as pilot:
            detail = app.query_one("#detail", DetailView)
            detail.show_task(task, cost=1.23)
            assert "My Task" in detail._content
            assert "task/abc-my-task" in detail._content
            assert "$1.23" in detail._content

    async def test_show_task_retry_count(self, app_env) -> None:
        app, repo = app_env
        epic = await repo.create_epic("Parent")
        task = await repo.create_task(epic.id, "Flaky Task")
        await repo.increment_retry(task.id)
        await repo.increment_retry(task.id)
        task = await repo.get_task(task.id)

        async with app.run_test(size=(160, 30)) as pilot:
            detail = app.query_one("#detail", DetailView)
            detail.show_task(task)
            assert "2/3" in detail._content

    async def test_clear_detail(self, app_env) -> None:
        app, repo = app_env
        epic = await repo.create_epic("Test")

        async with app.run_test(size=(160, 30)) as pilot:
            detail = app.query_one("#detail", DetailView)
            detail.show_epic(epic)
            assert "Test" in detail._content

            detail.clear_detail()
            assert detail._content == "Select a card to view details"


# ── Card widget ──


class TestTaskCardWidget:
    def test_card_renders_title(self) -> None:
        card = TaskCard(entity_type="task", entity_id="abc", title="My Card")
        rendered = card.render()
        assert "My Card" in rendered

    def test_card_renders_subtitle(self) -> None:
        card = TaskCard(
            entity_type="task", entity_id="abc",
            title="My Card", subtitle="Task R1",
        )
        rendered = card.render()
        assert "Task R1" in rendered

    def test_card_truncates_long_title(self) -> None:
        card = TaskCard(
            entity_type="task", entity_id="abc",
            title="A very long title that exceeds eighteen characters",
        )
        rendered = card.render()
        assert len(rendered.split("\n")[0]) <= 18

    def test_card_stores_entity_info(self) -> None:
        card = TaskCard(entity_type="epic", entity_id="xyz", title="Test")
        assert card.entity_type == "epic"
        assert card.entity_id == "xyz"

    def test_selected_message_carries_entity_info(self) -> None:
        msg = TaskCard.Selected(entity_type="task", entity_id="abc123")
        assert msg.entity_type == "task"
        assert msg.entity_id == "abc123"


# ── Board update mechanics ──


class TestBoardUpdate:
    async def test_update_board_clears_old_cards(self, app_env) -> None:
        """Cards from a previous refresh should be replaced, not duplicated."""
        app, repo = app_env
        await repo.create_epic("Original")

        async with app.run_test(size=(160, 30)) as pilot:
            await app._refresh_board()
            await pilot.pause()
            assert len(app.query(TaskCard)) == 1

            # Refresh again with same data — should still be 1 card
            await app._refresh_board()
            await pilot.pause()
            assert len(app.query(TaskCard)) == 1

    async def test_update_reflects_stage_changes(self, app_env) -> None:
        """If an entity's stage changes, it should move columns on refresh."""
        app, repo = app_env
        epic = await repo.create_epic("Moving epic")

        async with app.run_test(size=(160, 30)) as pilot:
            await app._refresh_board()
            await pilot.pause()

            cards = app.query(TaskCard)
            assert any(c.title_text == "Moving epic" for c in cards)

            await repo.update_epic_stage(epic.id, EpicStage.DESIGNING)
            await app._refresh_board()
            await pilot.pause()

            cards = app.query(TaskCard)
            epic_cards = [c for c in cards if c.title_text == "Moving epic"]
            assert len(epic_cards) == 1

    async def test_terminal_stage_tasks_leave_board(self, app_env) -> None:
        """Tasks in terminal stages (merged) don't have a column."""
        app, repo = app_env
        epic = await repo.create_epic("Parent")
        task = await repo.create_task(epic.id, "Doomed task")

        async with app.run_test(size=(160, 30)) as pilot:
            await app._refresh_board()
            await pilot.pause()

            task_cards = [c for c in app.query(TaskCard) if c.entity_type == "task"]
            assert len(task_cards) == 1

            await repo.update_task_stage(task.id, TaskStage.MERGED)
            await app._refresh_board()
            await pilot.pause()

            task_cards = [c for c in app.query(TaskCard) if c.entity_type == "task"]
            assert len(task_cards) == 0

    async def test_full_pipeline_spread(self, app_env) -> None:
        """Cards across many stages all render without error."""
        app, repo = app_env
        epic = await repo.create_epic("Big epic")
        await repo.update_epic_stage(epic.id, EpicStage.READY_FOR_PLANNING)

        stages = [
            TaskStage.PLANNING,
            TaskStage.IMPLEMENTING,
            TaskStage.VERIFYING,
            TaskStage.REVIEWING,
            TaskStage.UNIT_TESTING,
            TaskStage.INTEGRATION_TESTING,
            TaskStage.READY_FOR_MASTER,
        ]
        for i, stage in enumerate(stages):
            t = await repo.create_task(epic.id, f"Task {i}")
            await repo.update_task_stage(t.id, stage)

        async with app.run_test(size=(160, 30)) as pilot:
            await app._refresh_board()
            await pilot.pause()

            task_cards = [c for c in app.query(TaskCard) if c.entity_type == "task"]
            assert len(task_cards) == len(stages)


# ── Card click → detail integration ──


class TestCardDetailIntegration:
    async def test_clicking_epic_card_updates_detail(self, app_env) -> None:
        app, repo = app_env
        epic = await repo.create_epic("Clickable epic", "Epic desc")

        async with app.run_test(size=(160, 30)) as pilot:
            await app._refresh_board()
            await pilot.pause()

            # Directly call the detail handler (simulates the card message flow)
            await app._show_detail("epic", epic.id)
            await pilot.pause()

            detail = app.query_one("#detail", DetailView)
            assert "Clickable epic" in detail._content

    async def test_clicking_task_card_updates_detail(self, app_env) -> None:
        app, repo = app_env
        epic = await repo.create_epic("Parent")
        task = await repo.create_task(epic.id, "Clickable task")

        async with app.run_test(size=(160, 30)) as pilot:
            await app._refresh_board()
            await pilot.pause()

            await app._show_detail("task", task.id)
            await pilot.pause()

            detail = app.query_one("#detail", DetailView)
            assert "Clickable task" in detail._content
