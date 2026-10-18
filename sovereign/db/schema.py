"""SQLite schema definition and initialization."""

from __future__ import annotations

import aiosqlite

PRAGMA_STATEMENTS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
]

CREATE_TABLES = [
    # ── Epics ──
    """
    CREATE TABLE IF NOT EXISTS epics (
        id          TEXT PRIMARY KEY,
        title       TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        stage       TEXT NOT NULL DEFAULT 'backlog'
                    CHECK (stage IN ('backlog','designing','decomposing','ready_for_planning')),
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # ── Tasks ──
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id              TEXT PRIMARY KEY,
        epic_id         TEXT NOT NULL REFERENCES epics(id),
        title           TEXT NOT NULL,
        description     TEXT NOT NULL DEFAULT '',
        stage           TEXT NOT NULL DEFAULT 'planning'
                        CHECK (stage IN (
                            'planning','implementing','verifying','reviewing',
                            'merging_to_dev','unit_testing','integration_testing',
                            'docker_e2e_testing','ready_for_master','merged','failed'
                        )),
        branch_name     TEXT,
        worktree_path   TEXT,
        retry_count     INTEGER NOT NULL DEFAULT 0,
        dependencies    TEXT NOT NULL DEFAULT '[]',
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # ── Agent runs ──
    """
    CREATE TABLE IF NOT EXISTS agent_runs (
        id              TEXT PRIMARY KEY,
        task_id         TEXT REFERENCES tasks(id),
        epic_id         TEXT REFERENCES epics(id),
        role            TEXT NOT NULL,
        stage           TEXT NOT NULL,
        prompt          TEXT NOT NULL,
        output          TEXT,
        cost_usd        REAL,
        input_tokens    INTEGER,
        output_tokens   INTEGER,
        duration_sec    REAL,
        session_id      TEXT,
        status          TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running','completed','failed')),
        started_at      TEXT NOT NULL DEFAULT (datetime('now')),
        finished_at     TEXT
    )
    """,
    # ── Artifacts ──
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        id          TEXT PRIMARY KEY,
        task_id     TEXT REFERENCES tasks(id),
        epic_id     TEXT REFERENCES epics(id),
        run_id      TEXT REFERENCES agent_runs(id),
        kind        TEXT NOT NULL
                    CHECK (kind IN (
                        'design_doc','task_list','implementation_plan',
                        'code_diff','verification_report','review_report',
                        'test_result'
                    )),
        content     TEXT NOT NULL,
        created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # ── Stage log (audit trail) ──
    """
    CREATE TABLE IF NOT EXISTS stage_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL CHECK (entity_type IN ('epic','task')),
        entity_id   TEXT NOT NULL,
        from_stage  TEXT,
        to_stage    TEXT NOT NULL,
        reason      TEXT,
        created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
]

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tasks_epic_id ON tasks(epic_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_stage ON tasks(stage)",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_task_id ON agent_runs(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_epic_id ON agent_runs(epic_id)",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_task_id ON artifacts(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_epic_id ON artifacts(epic_id)",
    "CREATE INDEX IF NOT EXISTS idx_stage_log_entity ON stage_log(entity_type, entity_id)",
]


async def init_db(db_path: str) -> aiosqlite.Connection:
    """Initialize the database with schema and return the connection."""
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row

    for pragma in PRAGMA_STATEMENTS:
        await db.execute(pragma)

    for ddl in CREATE_TABLES:
        await db.execute(ddl)

    for idx in CREATE_INDEXES:
        await db.execute(idx)

    await db.commit()
    return db
