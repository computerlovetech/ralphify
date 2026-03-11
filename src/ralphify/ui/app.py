"""FastAPI application factory for the ralphify UI backend."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from queue import Empty

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ralphify._events import Event
from ralphify.manager import RunManager
from ralphify.ui.api import ws as ws_module
from ralphify.ui.api import runs as runs_module
from ralphify.ui.api import primitives as primitives_module
from ralphify.ui.api.ws import ws_manager
from ralphify.ui.persistence import Store


async def _drain_events(manager: RunManager, store: Store) -> None:
    """Background task: pull events from all run queues and fan out.

    Bridges the synchronous engine threads (which push events into
    ``queue.Queue``) to the async world (WebSocket broadcast + persistence).
    """
    while True:
        for managed in manager.list_runs():
            while True:
                try:
                    event: Event = managed.emitter.queue.get_nowait()
                except Empty:
                    break
                event_dict = event.to_dict()
                await ws_manager.broadcast(event.run_id, event_dict)
                await store.save_event(event_dict)
        await asyncio.sleep(0.05)


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Initialise shared state — stored on app.state so route handlers
        # can access it via FastAPI dependency injection (Request.app.state).
        manager = RunManager()
        app.state.manager = manager

        store = Store()
        await store.init()
        app.state.store = store

        # Start event drain task
        drain_task = asyncio.create_task(_drain_events(manager, store))

        yield

        # Cleanup
        drain_task.cancel()
        try:
            await drain_task
        except asyncio.CancelledError:
            pass
        await store.close()

    app = FastAPI(title="ralphify", lifespan=lifespan)

    # Mount API routers
    app.include_router(runs_module.router, prefix="/api", tags=["runs"])
    app.include_router(primitives_module.router, prefix="/api", tags=["primitives"])
    app.include_router(ws_module.router, prefix="/api", tags=["ws"])

    # Serve static frontend files
    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
