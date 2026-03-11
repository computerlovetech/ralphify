"""Tests for the SQLite persistence store."""

import asyncio
import json
from pathlib import Path

import pytest

from ralphify.ui.persistence import Store


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test_ui.db"


@pytest.fixture
def store(db_path):
    return Store(db_path=db_path)


def _run_async(coro):
    """Helper to run an async coroutine in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def event_loop():
    """Ensure a fresh event loop for each test."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


def _make_event(run_id="run-001", event_type="log_message", data=None, timestamp="2026-01-01T00:00:00Z"):
    return {
        "run_id": run_id,
        "type": event_type,
        "data": data or {},
        "timestamp": timestamp,
    }


class TestStoreInit:
    def test_init_creates_database_file(self, store, db_path):
        _run_async(store.init())
        _run_async(store.close())
        assert db_path.exists()

    def test_init_creates_parent_directories(self, tmp_path):
        db_path = tmp_path / "nested" / "dirs" / "ui.db"
        s = Store(db_path=db_path)
        _run_async(s.init())
        _run_async(s.close())
        assert db_path.exists()

    def test_init_creates_tables(self, store, db_path):
        import aiosqlite

        async def check_tables():
            await store.init()
            cursor = await store._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            rows = await cursor.fetchall()
            table_names = sorted(row["name"] for row in rows)
            await store.close()
            return table_names

        tables = _run_async(check_tables())
        assert "check_results" in tables
        assert "events" in tables
        assert "iterations" in tables
        assert "runs" in tables

    def test_init_is_idempotent(self, store, db_path):
        _run_async(store.init())
        # Calling init again should not raise
        _run_async(store.init())
        _run_async(store.close())


class TestSaveEvent:
    def test_save_event_stores_in_events_table(self, store):
        async def test():
            await store.init()
            event = _make_event()
            await store.save_event(event)

            events = await store.get_events("run-001")
            assert len(events) == 1
            assert events[0]["run_id"] == "run-001"
            assert events[0]["event_type"] == "log_message"
            await store.close()

        _run_async(test())

    def test_save_event_preserves_data(self, store):
        async def test():
            await store.init()
            event = _make_event(data={"key": "value", "number": 42})
            await store.save_event(event)

            events = await store.get_events("run-001")
            data = json.loads(events[0]["data"])
            assert data["key"] == "value"
            assert data["number"] == 42
            await store.close()

        _run_async(test())

    def test_save_run_started_creates_run(self, store):
        async def test():
            await store.init()
            event = _make_event(
                event_type="run_started",
                data={"command": "claude", "prompt_file": "PROMPT.md"},
                timestamp="2026-01-01T10:00:00Z",
            )
            await store.save_event(event)

            run = await store.get_run("run-001")
            assert run is not None
            assert run["status"] == "running"
            assert run["started_at"] == "2026-01-01T10:00:00Z"
            await store.close()

        _run_async(test())

    def test_save_run_stopped_updates_run(self, store):
        async def test():
            await store.init()
            # First create the run
            await store.save_event(_make_event(
                event_type="run_started",
                timestamp="2026-01-01T10:00:00Z",
            ))
            # Then stop it
            await store.save_event(_make_event(
                event_type="run_stopped",
                data={"reason": "completed", "completed": 5, "failed": 1, "timed_out": 0},
                timestamp="2026-01-01T10:05:00Z",
            ))

            run = await store.get_run("run-001")
            assert run["status"] == "completed"
            assert run["completed"] == 5
            assert run["failed"] == 1
            assert run["stopped_at"] == "2026-01-01T10:05:00Z"
            await store.close()

        _run_async(test())

    def test_save_iteration_started_creates_iteration(self, store):
        async def test():
            await store.init()
            await store.save_event(_make_event(event_type="run_started"))
            await store.save_event(_make_event(
                event_type="iteration_started",
                data={"iteration": 1},
                timestamp="2026-01-01T10:00:01Z",
            ))

            iterations = await store.get_iterations("run-001")
            assert len(iterations) == 1
            assert iterations[0]["iteration"] == 1
            assert iterations[0]["status"] == "started"
            await store.close()

        _run_async(test())

    def test_save_iteration_completed_updates_iteration(self, store):
        async def test():
            await store.init()
            await store.save_event(_make_event(event_type="run_started"))
            await store.save_event(_make_event(
                event_type="iteration_started",
                data={"iteration": 1},
                timestamp="2026-01-01T10:00:01Z",
            ))
            await store.save_event(_make_event(
                event_type="iteration_completed",
                data={"iteration": 1, "returncode": 0, "duration": 12.5},
                timestamp="2026-01-01T10:00:13Z",
            ))

            iterations = await store.get_iterations("run-001")
            assert len(iterations) == 1
            assert iterations[0]["status"] == "completed"
            assert iterations[0]["returncode"] == 0
            assert iterations[0]["duration"] == 12.5
            await store.close()

        _run_async(test())

    def test_save_check_passed(self, store):
        async def test():
            await store.init()
            await store.save_event(_make_event(event_type="run_started"))
            await store.save_event(_make_event(
                event_type="check_passed",
                data={"iteration": 1, "check_name": "pytest", "exit_code": 0, "timed_out": False},
            ))

            checks = await store.get_check_results("run-001", 1)
            assert len(checks) == 1
            assert checks[0]["check_name"] == "pytest"
            assert checks[0]["passed"] == 1
            assert checks[0]["exit_code"] == 0
            await store.close()

        _run_async(test())

    def test_save_check_failed(self, store):
        async def test():
            await store.init()
            await store.save_event(_make_event(event_type="run_started"))
            await store.save_event(_make_event(
                event_type="check_failed",
                data={"iteration": 2, "check_name": "mypy", "exit_code": 1, "timed_out": False},
            ))

            checks = await store.get_check_results("run-001", 2)
            assert len(checks) == 1
            assert checks[0]["check_name"] == "mypy"
            assert checks[0]["passed"] == 0
            assert checks[0]["exit_code"] == 1
            await store.close()

        _run_async(test())


class TestQueryHelpers:
    def test_get_run_returns_none_for_missing(self, store):
        async def test():
            await store.init()
            result = await store.get_run("nonexistent")
            assert result is None
            await store.close()

        _run_async(test())

    def test_list_runs_returns_all(self, store):
        async def test():
            await store.init()
            await store.save_event(_make_event(
                run_id="run-001",
                event_type="run_started",
                timestamp="2026-01-01T10:00:00Z",
            ))
            await store.save_event(_make_event(
                run_id="run-002",
                event_type="run_started",
                timestamp="2026-01-01T11:00:00Z",
            ))

            runs = await store.list_runs()
            assert len(runs) == 2
            # Should be ordered by started_at DESC
            assert runs[0]["run_id"] == "run-002"
            assert runs[1]["run_id"] == "run-001"
            await store.close()

        _run_async(test())

    def test_list_runs_empty(self, store):
        async def test():
            await store.init()
            runs = await store.list_runs()
            assert runs == []
            await store.close()

        _run_async(test())

    def test_get_iterations_ordered(self, store):
        async def test():
            await store.init()
            await store.save_event(_make_event(event_type="run_started"))
            for i in range(1, 4):
                await store.save_event(_make_event(
                    event_type="iteration_started",
                    data={"iteration": i},
                    timestamp=f"2026-01-01T10:00:0{i}Z",
                ))

            iterations = await store.get_iterations("run-001")
            assert len(iterations) == 3
            assert [it["iteration"] for it in iterations] == [1, 2, 3]
            await store.close()

        _run_async(test())

    def test_get_check_results_for_specific_iteration(self, store):
        async def test():
            await store.init()
            await store.save_event(_make_event(event_type="run_started"))
            # Checks for iteration 1
            await store.save_event(_make_event(
                event_type="check_passed",
                data={"iteration": 1, "check_name": "pytest", "exit_code": 0},
            ))
            # Checks for iteration 2
            await store.save_event(_make_event(
                event_type="check_failed",
                data={"iteration": 2, "check_name": "mypy", "exit_code": 1},
            ))

            checks_1 = await store.get_check_results("run-001", 1)
            checks_2 = await store.get_check_results("run-001", 2)
            assert len(checks_1) == 1
            assert checks_1[0]["check_name"] == "pytest"
            assert len(checks_2) == 1
            assert checks_2[0]["check_name"] == "mypy"
            await store.close()

        _run_async(test())

    def test_get_events_with_limit_and_offset(self, store):
        async def test():
            await store.init()
            # Insert 5 events
            for i in range(5):
                await store.save_event(_make_event(
                    event_type="log_message",
                    data={"index": i},
                    timestamp=f"2026-01-01T10:00:0{i}Z",
                ))

            # Get with limit
            events = await store.get_events("run-001", limit=2)
            assert len(events) == 2

            # Get with offset
            events = await store.get_events("run-001", limit=2, offset=2)
            assert len(events) == 2
            data = json.loads(events[0]["data"])
            assert data["index"] == 2
            await store.close()

        _run_async(test())
