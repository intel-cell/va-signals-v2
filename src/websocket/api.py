"""WebSocket API endpoints for real-time signal push."""

import uuid
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, Depends
from pydantic import BaseModel

from .manager import ws_manager
from ..auth.rbac import RoleChecker
from ..auth.models import UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])


class SubscriptionRequest(BaseModel):
    """Request to subscribe/unsubscribe from topics."""
    topics: list[str]


class BroadcastRequest(BaseModel):
    """Request to broadcast a message (admin only)."""
    message: dict
    topic: str = "all"


@router.websocket("/signals")
async def websocket_signals(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None, description="Client identifier"),
    token: Optional[str] = Query(None, description="Auth token"),
):
    """
    WebSocket endpoint for real-time signal notifications.

    Connect to receive live updates when:
    - New signals are detected
    - Alerts are triggered
    - Oversight events occur
    - Battlefield status changes

    Query Parameters:
    - client_id: Optional client identifier (generated if not provided)
    - token: Optional authentication token

    Message Format (outgoing):
    {
        "type": "signal" | "alert" | "oversight" | "battlefield" | "ping",
        "topic": "signals" | "alerts" | "oversight" | "battlefield" | "all",
        "timestamp": "2026-02-04T12:00:00Z",
        "data": { ... }
    }

    Message Format (incoming - commands):
    {
        "action": "subscribe" | "unsubscribe" | "pong",
        "topics": ["signals", "alerts", ...]
    }
    """
    # Generate client_id if not provided
    if not client_id:
        client_id = f"client_{uuid.uuid4().hex[:12]}"

    # Extract user_id from token if provided (simplified - real auth would verify token)
    user_id = None
    if token:
        # In production, this would validate the token and extract user info
        user_id = f"user_{token[:8]}" if len(token) >= 8 else None

    await ws_manager.connect(websocket, client_id, user_id)

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "client_id": client_id,
            "message": "Connected to VA Signals real-time feed",
            "available_topics": ["signals", "alerts", "oversight", "battlefield", "all"]
        })

        while True:
            # Receive and process commands from client
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                action = message.get("action")

                if action == "subscribe":
                    topics = message.get("topics", [])
                    await ws_manager.subscribe(client_id, topics)
                    await websocket.send_json({
                        "type": "subscribed",
                        "topics": topics
                    })

                elif action == "unsubscribe":
                    topics = message.get("topics", [])
                    await ws_manager.unsubscribe(client_id, topics)
                    await websocket.send_json({
                        "type": "unsubscribed",
                        "topics": topics
                    })

                elif action == "pong":
                    # Client responding to ping
                    pass

                elif action == "status":
                    # Client requesting connection status
                    await websocket.send_json({
                        "type": "status",
                        "client_id": client_id,
                        "user_id": user_id,
                        "connections_count": ws_manager.get_connection_count()
                    })

                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown action: {action}"
                    })

            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON"
                })

    except WebSocketDisconnect:
        await ws_manager.disconnect(client_id)
        logger.info(f"Client {client_id} disconnected")


@router.get("/connections", summary="Get active WebSocket connections")
async def get_connections(_: None = Depends(RoleChecker(UserRole.ANALYST))):
    """Get information about active WebSocket connections. Requires ANALYST role."""
    return {
        "count": ws_manager.get_connection_count(),
        "connections": ws_manager.get_connection_info()
    }


@router.post("/broadcast", summary="Broadcast a message to connected clients")
async def broadcast_message(
    request: BroadcastRequest,
    _: None = Depends(RoleChecker(UserRole.COMMANDER)),
):
    """Broadcast a message to all connected clients. Requires COMMANDER role."""
    sent_count = await ws_manager.broadcast(request.message, request.topic)
    return {
        "success": True,
        "sent_to": sent_count,
        "topic": request.topic
    }


@router.post("/test-signal", summary="Send a test signal for WebSocket testing")
async def send_test_signal(_: None = Depends(RoleChecker(UserRole.ANALYST))):
    """Send a test signal notification to all subscribed clients. For testing only."""
    test_signal = {
        "signal_id": "test_signal_001",
        "type": "TEST",
        "title": "Test Signal - WebSocket Connection Verified",
        "severity": "low",
        "source": "websocket_test",
        "message": "This is a test signal to verify WebSocket connectivity."
    }
    sent_count = await ws_manager.broadcast_signal(test_signal)
    return {
        "success": True,
        "sent_to": sent_count,
        "signal": test_signal
    }


@router.get("/health", summary="WebSocket service health check")
async def websocket_health():
    """Check WebSocket service health."""
    return {
        "status": "healthy",
        "active_connections": ws_manager.get_connection_count()
    }
