"""WebSocket module for real-time signal push notifications."""

from .manager import ConnectionManager, ws_manager
from .api import router as websocket_router
from .broadcast import (
    notify_new_signal,
    notify_alert,
    notify_oversight_event,
    notify_battlefield_update,
    notify_source_health,
    notify_new_signal_sync,
    notify_alert_sync,
)

__all__ = [
    "ConnectionManager",
    "ws_manager",
    "websocket_router",
    "notify_new_signal",
    "notify_alert",
    "notify_oversight_event",
    "notify_battlefield_update",
    "notify_source_health",
    "notify_new_signal_sync",
    "notify_alert_sync",
]
