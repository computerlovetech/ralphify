"""WebSocket endpoint for live event streaming."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class WebSocketManager:
    """Manages WebSocket connections and event fan-out."""

    def __init__(self) -> None:
        self._connections: dict[WebSocket, set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        """Accept a new WebSocket connection and subscribe it to all runs.

        New connections receive events from every run by default (wildcard
        ``"*"`` subscription).  Clients can narrow this with ``subscribe``
        and ``unsubscribe`` messages.
        """
        await ws.accept()
        async with self._lock:
            self._connections[ws] = {"*"}  # subscribe to all by default

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket connection and all its subscriptions."""
        async with self._lock:
            self._connections.pop(ws, None)

    async def subscribe(self, ws: WebSocket, run_id: str) -> None:
        """Add a run-specific subscription for a connected WebSocket.

        Use ``"*"`` to subscribe to all runs.  Multiple subscriptions are
        additive — the client receives events matching *any* of them.
        """
        async with self._lock:
            if ws in self._connections:
                self._connections[ws].add(run_id)

    async def unsubscribe(self, ws: WebSocket, run_id: str) -> None:
        """Remove a run-specific subscription for a connected WebSocket."""
        async with self._lock:
            if ws in self._connections:
                self._connections[ws].discard(run_id)

    async def broadcast(self, run_id: str, data: dict) -> None:
        """Send an event to all WebSocket clients subscribed to the given run.

        Clients subscribed to ``"*"`` (wildcard) receive events from every
        run.  Disconnected or errored sockets are cleaned up automatically.
        """
        async with self._lock:
            targets = list(self._connections.items())
        for ws, subs in targets:
            if "*" in subs or run_id in subs:
                try:
                    await ws.send_json(data)
                except Exception:
                    await self.disconnect(ws)


# Instance created at app startup
ws_manager = WebSocketManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Handle a WebSocket connection for live event streaming.

    Clients send JSON messages with ``{"action": "subscribe"|"unsubscribe",
    "run_id": "<id>"}`` to filter which runs they receive events for.
    By default, new connections receive events from all runs.
    """
    await ws_manager.connect(ws)
    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")
            run_id = msg.get("run_id", "*")
            if action == "subscribe":
                await ws_manager.subscribe(ws, run_id)
            elif action == "unsubscribe":
                await ws_manager.unsubscribe(ws, run_id)
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)
