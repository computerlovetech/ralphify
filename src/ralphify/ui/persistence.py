"""SQLite persistence for the UI layer.

Stores run history, iterations, check results, and raw events in a local
SQLite database at ``~/.ralph/ui.db``.  All access is async via aiosqlite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

DEFAULT_DB_PATH = Path.home() / ".ralph" / "ui.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'pending',
    command      TEXT NOT NULL DEFAULT '',
    prompt_file  TEXT NOT NULL DEFAULT '',
    started_at   TEXT,
    stopped_at   TEXT,
    iterations   INTEGER NOT NULL DEFAULT 0,
    completed    INTEGER NOT NULL DEFAULT 0,
    failed       INTEGER NOT NULL DEFAULT 0,
    timed_out    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS iterations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    iteration    INTEGER NOT NULL,
    status       TEXT NOT NULL DEFAULT 'started',
    returncode   INTEGER,
    duration     REAL,
    started_at   TEXT,
    finished_at  TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS check_results (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    iteration    INTEGER NOT NULL,
    check_name   TEXT NOT NULL,
    passed       INTEGER NOT NULL,
    exit_code    INTEGER,
    timed_out    INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    data         TEXT NOT NULL DEFAULT '{}',
    timestamp    TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
"""


class Store:
    """Async SQLite store for run history and events."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Open the database and create tables if they don't exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Event ingestion
    # ------------------------------------------------------------------

    async def save_event(self, event: dict[str, Any]) -> None:
        """Persist a raw event and update materialized views.

        ``event`` should have keys: ``run_id``, ``type``, ``data``, ``timestamp``.
        """
        assert self._db is not None
        run_id = event["run_id"]
        event_type = event["type"]
        data = event.get("data", {})
        timestamp = event["timestamp"]

        # Append to events table
        await self._db.execute(
            "INSERT INTO events (run_id, event_type, data, timestamp) VALUES (?, ?, ?, ?)",
            (run_id, event_type, json.dumps(data), timestamp),
        )

        # Upsert materialized views based on event type
        if event_type == "run_started":
            await self._db.execute(
                "INSERT OR IGNORE INTO runs (run_id) VALUES (?)",
                (run_id,),
            )
            await self._db.execute(
                "UPDATE runs SET status = 'running', started_at = ?, "
                "command = ?, prompt_file = ? WHERE run_id = ?",
                (
                    timestamp,
                    data.get("command", ""),
                    data.get("prompt_file", ""),
                    run_id,
                ),
            )

        elif event_type == "run_stopped":
            await self._db.execute(
                "UPDATE runs SET status = ?, stopped_at = ?, "
                "completed = ?, failed = ?, timed_out = ? WHERE run_id = ?",
                (
                    data.get("reason", "stopped"),
                    timestamp,
                    data.get("completed", 0),
                    data.get("failed", 0),
                    data.get("timed_out", 0),
                    run_id,
                ),
            )

        elif event_type == "iteration_started":
            iteration = data.get("iteration", 0)
            await self._db.execute(
                "INSERT INTO iterations (run_id, iteration, status, started_at) "
                "VALUES (?, ?, 'started', ?)",
                (run_id, iteration, timestamp),
            )
            await self._db.execute(
                "UPDATE runs SET iterations = ? WHERE run_id = ?",
                (iteration, run_id),
            )

        elif event_type in (
            "iteration_completed",
            "iteration_failed",
            "iteration_timed_out",
        ):
            iteration = data.get("iteration", 0)
            status = event_type.replace("iteration_", "")
            await self._db.execute(
                "UPDATE iterations SET status = ?, returncode = ?, "
                "duration = ?, finished_at = ? "
                "WHERE run_id = ? AND iteration = ?",
                (
                    status,
                    data.get("returncode"),
                    data.get("duration"),
                    timestamp,
                    run_id,
                    iteration,
                ),
            )

        elif event_type in ("check_passed", "check_failed"):
            iteration = data.get("iteration", 0)
            await self._db.execute(
                "INSERT INTO check_results "
                "(run_id, iteration, check_name, passed, exit_code, timed_out) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    iteration,
                    data.get("check_name", ""),
                    1 if event_type == "check_passed" else 0,
                    data.get("exit_code"),
                    1 if data.get("timed_out") else 0,
                ),
            )

        await self._db.commit()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return a run summary dict or ``None``."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def list_runs(self) -> list[dict[str, Any]]:
        """Return all runs ordered by start time descending."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM runs ORDER BY started_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_iterations(self, run_id: str) -> list[dict[str, Any]]:
        """Return iterations for a run ordered by iteration number."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM iterations WHERE run_id = ? ORDER BY iteration",
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_check_results(
        self, run_id: str, iteration: int
    ) -> list[dict[str, Any]]:
        """Return check results for a specific iteration."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM check_results WHERE run_id = ? AND iteration = ? "
            "ORDER BY id",
            (run_id, iteration),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_events(
        self, run_id: str, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Return raw events for a run."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY id LIMIT ? OFFSET ?",
            (run_id, limit, offset),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
