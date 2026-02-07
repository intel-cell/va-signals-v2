"""
API endpoints for resilience monitoring.

Provides visibility into circuit breaker states, rate limits,
and retry statistics.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from ..auth.models import UserRole
from ..auth.rbac import RoleChecker
from .circuit_breaker import CircuitBreaker, CircuitState
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resilience", tags=["Resilience"])


@router.get("/circuits", summary="List all circuit breakers")
async def list_circuits(_: None = Depends(RoleChecker(UserRole.ANALYST))):
    """
    Get status of all circuit breakers.

    Returns state, metrics, and configuration for each circuit.
    Requires ANALYST role.
    """
    circuits = CircuitBreaker.all()
    return {"circuits": [cb.to_dict() for cb in circuits.values()], "count": len(circuits)}


@router.get("/circuits/{name}", summary="Get circuit breaker status")
async def get_circuit(name: str, _: None = Depends(RoleChecker(UserRole.ANALYST))):
    """Get status of a specific circuit breaker."""
    cb = CircuitBreaker.get(name)
    if not cb:
        raise HTTPException(status_code=404, detail=f"Circuit '{name}' not found")
    return cb.to_dict()


@router.post("/circuits/{name}/reset", summary="Reset a circuit breaker")
async def reset_circuit(name: str, _: None = Depends(RoleChecker(UserRole.COMMANDER))):
    """
    Manually reset a circuit breaker to CLOSED state.

    Use with caution - only when you've verified the downstream
    service has recovered.

    Requires COMMANDER role.
    """
    cb = CircuitBreaker.get(name)
    if not cb:
        raise HTTPException(status_code=404, detail=f"Circuit '{name}' not found")

    old_state = cb.state
    cb.reset()

    return {
        "success": True,
        "circuit": name,
        "previous_state": old_state.value,
        "current_state": cb.state.value,
        "message": f"Circuit '{name}' has been reset",
    }


@router.get("/rate-limits", summary="List all rate limiters")
async def list_rate_limits(_: None = Depends(RoleChecker(UserRole.ANALYST))):
    """
    Get status of all rate limiters.

    Shows current token availability and usage statistics.
    Requires ANALYST role.
    """
    limiters = RateLimiter.all()
    return {"rate_limiters": [rl.to_dict() for rl in limiters.values()], "count": len(limiters)}


@router.get("/rate-limits/{name}", summary="Get rate limiter status")
async def get_rate_limit(name: str, _: None = Depends(RoleChecker(UserRole.ANALYST))):
    """Get status of a specific rate limiter."""
    rl = RateLimiter.get(name)
    if not rl:
        raise HTTPException(status_code=404, detail=f"Rate limiter '{name}' not found")
    return rl.to_dict()


@router.get("/health", summary="Resilience system health")
async def resilience_health():
    """
    Get overall health of resilience components.

    Checks for any open circuit breakers or exhausted rate limits.
    """
    circuits = CircuitBreaker.all()
    limiters = RateLimiter.all()

    open_circuits = [name for name, cb in circuits.items() if cb.state == CircuitState.OPEN]

    exhausted_limiters = [name for name, rl in limiters.items() if rl.available_tokens < 1]

    health_status = "healthy"
    if open_circuits:
        health_status = "degraded"
    if exhausted_limiters:
        health_status = "degraded" if health_status == "healthy" else health_status

    return {
        "status": health_status,
        "circuits": {
            "total": len(circuits),
            "open": len(open_circuits),
            "open_names": open_circuits,
        },
        "rate_limits": {
            "total": len(limiters),
            "exhausted": len(exhausted_limiters),
            "exhausted_names": exhausted_limiters,
        },
    }


@router.get("/summary", summary="Resilience summary dashboard")
async def resilience_summary(_: None = Depends(RoleChecker(UserRole.VIEWER))):
    """
    Get summary of all resilience components for dashboard.

    Requires VIEWER role.
    """
    circuits = CircuitBreaker.all()
    limiters = RateLimiter.all()

    circuit_summary = {
        "closed": 0,
        "open": 0,
        "half_open": 0,
        "total_calls": 0,
        "total_failures": 0,
        "total_rejections": 0,
    }

    for cb in circuits.values():
        if cb.state == CircuitState.CLOSED:
            circuit_summary["closed"] += 1
        elif cb.state == CircuitState.OPEN:
            circuit_summary["open"] += 1
        else:
            circuit_summary["half_open"] += 1
        circuit_summary["total_calls"] += cb.metrics.total_calls
        circuit_summary["total_failures"] += cb.metrics.failed_calls
        circuit_summary["total_rejections"] += cb.metrics.rejected_calls

    limiter_summary = {
        "total": len(limiters),
        "total_allowed": sum(rl._state.total_allowed for rl in limiters.values()),
        "total_denied": sum(rl._state.total_denied for rl in limiters.values()),
    }

    return {
        "circuits": circuit_summary,
        "rate_limits": limiter_summary,
    }
