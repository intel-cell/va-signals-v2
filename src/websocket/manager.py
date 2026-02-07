"""WebSocket connection manager for real-time signal broadcasting."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """Metadata about a WebSocket connection."""

    websocket: WebSocket
    user_id: str | None = None
    subscriptions: set = field(default_factory=set)
    connected_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.

    Supports:
    - Multiple concurrent connections
    - Topic-based subscriptions (signals, alerts, oversight, battlefield)
    - Broadcast to all or filtered connections
    - Connection health monitoring
    """

    def __init__(self):
        self.active_connections: dict[str, ConnectionInfo] = {}
        self._lock = asyncio.Lock()
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._broadcaster_task: asyncio.Task | None = None

    async def connect(
        self, websocket: WebSocket, client_id: str, user_id: str | None = None
    ) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections[client_id] = ConnectionInfo(
                websocket=websocket,
                user_id=user_id,
                subscriptions={"all"},  # Default subscription
            )
        logger.info(f"WebSocket connected: {client_id}, user: {user_id}")

    async def disconnect(self, client_id: str) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if client_id in self.active_connections:
                del self.active_connections[client_id]
        logger.info(f"WebSocket disconnected: {client_id}")

    async def subscribe(self, client_id: str, topics: list[str]) -> None:
        """Subscribe a client to specific topics."""
        async with self._lock:
            if client_id in self.active_connections:
                self.active_connections[client_id].subscriptions.update(topics)
                logger.info(f"Client {client_id} subscribed to: {topics}")

    async def unsubscribe(self, client_id: str, topics: list[str]) -> None:
        """Unsubscribe a client from specific topics."""
        async with self._lock:
            if client_id in self.active_connections:
                self.active_connections[client_id].subscriptions.difference_update(topics)
                logger.info(f"Client {client_id} unsubscribed from: {topics}")

    async def send_personal(self, client_id: str, message: dict[str, Any]) -> bool:
        """Send a message to a specific client."""
        async with self._lock:
            conn_info = self.active_connections.get(client_id)
            if not conn_info:
                return False

        try:
            await conn_info.websocket.send_json(message)
            return True
        except Exception as e:
            logger.error(f"Error sending to {client_id}: {e}")
            await self.disconnect(client_id)
            return False

    async def broadcast(self, message: dict[str, Any], topic: str = "all") -> int:
        """
        Broadcast a message to all subscribed connections.

        Args:
            message: The message to broadcast
            topic: The topic to broadcast to (clients must be subscribed)

        Returns:
            Number of clients that received the message
        """
        message["timestamp"] = datetime.now(UTC).isoformat()
        message["topic"] = topic

        sent_count = 0
        disconnected = []

        async with self._lock:
            clients = list(self.active_connections.items())

        for client_id, conn_info in clients:
            # Check if client is subscribed to this topic
            if (
                topic != "all"
                and topic not in conn_info.subscriptions
                and "all" not in conn_info.subscriptions
            ):
                continue

            try:
                await conn_info.websocket.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.error(f"Error broadcasting to {client_id}: {e}")
                disconnected.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected:
            await self.disconnect(client_id)

        if sent_count > 0:
            logger.info(f"Broadcast to {sent_count} clients on topic '{topic}'")

        return sent_count

    async def broadcast_signal(self, signal: dict[str, Any]) -> int:
        """Broadcast a new signal alert."""
        return await self.broadcast({"type": "signal", "data": signal}, topic="signals")

    async def broadcast_alert(self, alert: dict[str, Any]) -> int:
        """Broadcast a system alert."""
        return await self.broadcast({"type": "alert", "data": alert}, topic="alerts")

    async def broadcast_oversight(self, event: dict[str, Any]) -> int:
        """Broadcast an oversight event."""
        return await self.broadcast({"type": "oversight", "data": event}, topic="oversight")

    async def broadcast_battlefield(self, update: dict[str, Any]) -> int:
        """Broadcast a battlefield status update."""
        return await self.broadcast({"type": "battlefield", "data": update}, topic="battlefield")

    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.active_connections)

    def get_connection_info(self) -> list[dict[str, Any]]:
        """Get info about all active connections (for monitoring)."""
        return [
            {
                "client_id": client_id,
                "user_id": conn.user_id,
                "subscriptions": list(conn.subscriptions),
                "connected_at": conn.connected_at,
            }
            for client_id, conn in self.active_connections.items()
        ]

    async def ping_all(self) -> dict[str, bool]:
        """Ping all connections to check health."""
        results = {}
        disconnected = []

        async with self._lock:
            clients = list(self.active_connections.items())

        for client_id, conn_info in clients:
            try:
                await conn_info.websocket.send_json({"type": "ping"})
                results[client_id] = True
            except Exception:
                results[client_id] = False
                disconnected.append(client_id)

        for client_id in disconnected:
            await self.disconnect(client_id)

        return results


# Global singleton instance
ws_manager = ConnectionManager()
