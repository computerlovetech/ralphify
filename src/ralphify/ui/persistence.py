"""SQLite persistence for the UI layer.

Stores run history, iterations, check results, and raw events in a local
SQLite database at ``~/.ralph/ui.db``.  All access is async via aiosqlite.
"""

from __future__ import annotations

import json
from pathlib import Path
from collections.abc import Callable
from typing import Any

import aiosqlite

from ralphify._events import EventType

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


# Maps iteration-end event types to their database status values.
# Explicit mapping avoids deriving status from event names via string
# manipulation, which would break silently if event names changed.
_ITERATION_STATUS: dict[EventType, str] = {
    EventType.ITERATION_COMPLETED: "completed",
    EventType.ITERATION_FAILED: "failed",
    EventType.ITERATION_TIMED_OUT: "timed_out",
}


class Store:
    """Async SQLite store for run history and events."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._db: aiosqlite.Connection | None = None
        self._event_handlers: dict[EventType, Callable[..., Any]] = {
            EventType.RUN_STARTED: self._on_run_started,
            EventType.RUN_STOPPED: self._on_run_stopped,
            EventType.ITERATION_STARTED: self._on_iteration_started,
            EventType.ITERATION_COMPLETED: self._on_iteration_ended,
            EventType.ITERATION_FAILED: self._on_iteration_ended,
            EventType.ITERATION_TIMED_OUT: self._on_iteration_ended,
            EventType.CHECK_PASSED: self._on_check_result,
            EventType.CHECK_FAILED: self._on_check_result,
        }

    async def init(self) -> None:
        """Open the database and create tables if they don't exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    @property
    def _conn(self) -> aiosqlite.Connection:
        """Return the active database connection.

        Raises ``RuntimeError`` if ``init()`` has not been called.
        """
        if self._db is None:
            raise RuntimeError("Store not initialised — call init() first")
        return self._db

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
        db = self._conn
        run_id = event["run_id"]
        event_type_str = event["type"]
        data = event.get("data", {})
        timestamp = event["timestamp"]

        # Append to events table (store the string value for SQL portability)
        await db.execute(
            "INSERT INTO events (run_id, event_type, data, timestamp) VALUES (?, ?, ?, ?)",
            (run_id, event_type_str, json.dumps(data), timestamp),
        )

        # Convert to enum for type-safe handler dispatch
        try:
            event_type = EventType(event_type_str)
        except ValueError:
            await db.commit()
            return

        handler = self._event_handlers.get(event_type)
        if handler:
            await handler(event_type, run_id, data, timestamp)

        await db.commit()

    async def _on_run_started(
        self, event_type: EventType, run_id: str, data: dict[str, Any], timestamp: str,
    ) -> None:
        db = self._conn
        await db.execute(
            "INSERT OR IGNORE INTO runs (run_id) VALUES (?)",
            (run_id,),
        )
        await db.execute(
            "UPDATE runs SET status = 'running', started_at = ?, "
            "command = ?, prompt_file = ? WHERE run_id = ?",
            (timestamp, data.get("command", ""), data.get("prompt_file", ""), run_id),
        )

    async def _on_run_stopped(
        self, event_type: EventType, run_id: str, data: dict[str, Any], timestamp: str,
    ) -> None:
        db = self._conn
        await db.execute(
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

    async def _on_iteration_started(
        self, event_type: EventType, run_id: str, data: dict[str, Any], timestamp: str,
    ) -> None:
        db = self._conn
        iteration = data.get("iteration", 0)
        await db.execute(
            "INSERT INTO iterations (run_id, iteration, status, started_at) "
            "VALUES (?, ?, 'started', ?)",
            (run_id, iteration, timestamp),
        )
        await db.execute(
            "UPDATE runs SET iterations = ? WHERE run_id = ?",
            (iteration, run_id),
        )

    async def _on_iteration_ended(
        self, event_type: EventType, run_id: str, data: dict[str, Any], timestamp: str,
    ) -> None:
        db = self._conn
        iteration = data.get("iteration", 0)
        status = _ITERATION_STATUS[event_type]
        await db.execute(
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

    async def _on_check_result(
        self, event_type: EventType, run_id: str, data: dict[str, Any], timestamp: str,
    ) -> None:
        db = self._conn
        iteration = data.get("iteration", 0)
        await db.execute(
            "INSERT INTO check_results "
            "(run_id, iteration, check_name, passed, exit_code, timed_out) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                iteration,
                data.get("name", ""),
                1 if event_type == EventType.CHECK_PASSED else 0,
                data.get("exit_code"),
                1 if data.get("timed_out") else 0,
            ),
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def _fetch_one(self, query: str, params: tuple = ()) -> dict[str, Any] | None:
        """Execute *query* and return the first row as a dict, or ``None``."""
        cursor = await self._conn.execute(query, params)
        row = await cursor.fetchone()
        return dict(row) if row is not None else None

    async def _fetch_all(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute *query* and return all rows as dicts."""
        cursor = await self._conn.execute(query, params)
        return [dict(r) for r in await cursor.fetchall()]

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return a run summary dict or ``None``."""
        return await self._fetch_one(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,),
        )

    async def list_runs(self) -> list[dict[str, Any]]:
        """Return all runs ordered by start time descending."""
        return await self._fetch_all(
            "SELECT * FROM runs ORDER BY started_at DESC",
        )

    async def get_iterations(self, run_id: str) -> list[dict[str, Any]]:
        """Return iterations for a run ordered by iteration number."""
        return await self._fetch_all(
            "SELECT * FROM iterations WHERE run_id = ? ORDER BY iteration",
            (run_id,),
        )

    async def get_check_results(
        self, run_id: str, iteration: int,
    ) -> list[dict[str, Any]]:
        """Return check results for a specific iteration."""
        return await self._fetch_all(
            "SELECT * FROM check_results WHERE run_id = ? AND iteration = ? "
            "ORDER BY id",
            (run_id, iteration),
        )

    async def get_events(
        self, run_id: str, limit: int = 100, offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return raw events for a run."""
        return await self._fetch_all(
            "SELECT * FROM events WHERE run_id = ? ORDER BY id LIMIT ? OFFSET ?",
            (run_id, limit, offset),
        )
