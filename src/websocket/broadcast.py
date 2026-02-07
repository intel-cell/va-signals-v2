"""
Helper functions for broadcasting events from anywhere in the application.

These functions can be imported and called when signals are detected,
alerts are triggered, or status changes occur.

Usage:
    from src.websocket.broadcast import notify_new_signal

    async def detect_signal():
        signal = {"id": "123", "title": "New regulation"}
        # ... detection logic ...
        await notify_new_signal(signal)
"""

import asyncio
import logging
from typing import Any

from .manager import ws_manager

logger = logging.getLogger(__name__)


async def notify_new_signal(signal: dict[str, Any]) -> int:
    """
    Notify all subscribed clients about a new signal.

    Args:
        signal: Signal data including id, title, severity, etc.

    Returns:
        Number of clients notified
    """
    return await ws_manager.broadcast_signal(signal)


async def notify_alert(
    alert_type: str, title: str, message: str, severity: str = "info", data: dict | None = None
) -> int:
    """
    Send an alert notification to all connected clients.

    Args:
        alert_type: Type of alert (source_failure, high_severity, threshold, etc.)
        title: Alert title
        message: Alert message
        severity: Alert severity (info, warning, error, critical)
        data: Additional data to include

    Returns:
        Number of clients notified
    """
    alert = {
        "alert_type": alert_type,
        "title": title,
        "message": message,
        "severity": severity,
        **(data or {}),
    }
    return await ws_manager.broadcast_alert(alert)


async def notify_oversight_event(event: dict[str, Any]) -> int:
    """
    Notify about a new oversight event.

    Args:
        event: Oversight event data

    Returns:
        Number of clients notified
    """
    return await ws_manager.broadcast_oversight(event)


async def notify_battlefield_update(update: dict[str, Any]) -> int:
    """
    Notify about a battlefield status change.

    Args:
        update: Battlefield update data (vehicle status change, gate hit, etc.)

    Returns:
        Number of clients notified
    """
    return await ws_manager.broadcast_battlefield(update)


async def notify_source_health(source_id: str, status: str, details: dict | None = None) -> int:
    """
    Notify about a source health change.

    Args:
        source_id: ID of the source
        status: New status (healthy, warning, error)
        details: Additional details

    Returns:
        Number of clients notified
    """
    return await ws_manager.broadcast(
        {
            "type": "source_health",
            "data": {"source_id": source_id, "status": status, **(details or {})},
        },
        topic="alerts",
    )


def notify_sync(func):
    """
    Decorator for synchronous code that needs to send notifications.

    Usage:
        @notify_sync
        def process_signal(signal):
            # ... processing ...
            return notify_new_signal(signal)
    """

    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule the coroutine to run in the existing loop
            asyncio.create_task(func(*args, **kwargs))
        else:
            # Run in a new loop
            loop.run_until_complete(func(*args, **kwargs))

    return wrapper


# Synchronous wrappers for use in non-async code
def notify_new_signal_sync(signal: dict[str, Any]) -> None:
    """Synchronous version of notify_new_signal."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(notify_new_signal(signal))
        else:
            loop.run_until_complete(notify_new_signal(signal))
    except RuntimeError:
        # No event loop, create one
        asyncio.run(notify_new_signal(signal))


def notify_alert_sync(
    alert_type: str, title: str, message: str, severity: str = "info", data: dict | None = None
) -> None:
    """Synchronous version of notify_alert."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(notify_alert(alert_type, title, message, severity, data))
        else:
            loop.run_until_complete(notify_alert(alert_type, title, message, severity, data))
    except RuntimeError:
        asyncio.run(notify_alert(alert_type, title, message, severity, data))
