"""
Tenant middleware for request scoping.

Extracts tenant context from requests and makes it available
to all downstream handlers.
"""

import logging
from contextvars import ContextVar

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from .manager import tenant_manager
from .models import TenantContext

logger = logging.getLogger(__name__)

# Context variable for current tenant (thread-safe)
_tenant_context: ContextVar[TenantContext | None] = ContextVar("tenant_context", default=None)


def get_tenant_context() -> TenantContext | None:
    """
    Get the current tenant context.

    Returns None if no tenant context is set (e.g., public endpoints).
    """
    return _tenant_context.get()


def set_tenant_context(context: TenantContext | None) -> None:
    """Set the current tenant context."""
    _tenant_context.set(context)


def require_tenant_context() -> TenantContext:
    """
    Get the current tenant context, raising an error if not set.

    Use this in endpoints that require tenant scoping.
    """
    context = _tenant_context.get()
    if not context:
        raise HTTPException(
            status_code=400, detail="Tenant context required. Include X-Tenant-ID header."
        )
    return context


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract and validate tenant context from requests.

    Tenant can be identified via:
    1. X-Tenant-ID header (explicit tenant ID)
    2. X-Tenant-Slug header (URL-safe slug)
    3. Subdomain (if configured)
    4. User's primary tenant (fallback)

    Public endpoints (health, docs, etc.) bypass tenant validation.
    """

    # Endpoints that don't require tenant context
    PUBLIC_PATHS = {
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/metrics",
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/verify",
    }

    # Path prefixes that are always public
    PUBLIC_PREFIXES = (
        "/static/",
        "/ws/",  # WebSocket handles its own auth
    )

    async def dispatch(self, request: Request, call_next):
        # Skip tenant resolution for public paths
        path = request.url.path
        if path in self.PUBLIC_PATHS or path.startswith(self.PUBLIC_PREFIXES):
            return await call_next(request)

        # Get user info from auth middleware (must run after auth)
        user_id = getattr(request.state, "user_id", None)
        getattr(request.state, "user_email", None)

        if not user_id:
            # No authenticated user, skip tenant resolution
            return await call_next(request)

        try:
            # Try to resolve tenant context
            context = await self._resolve_tenant(request, user_id)

            if context:
                set_tenant_context(context)
                # Also attach to request.state for easy access
                request.state.tenant_context = context
                request.state.tenant_id = context.tenant_id

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error resolving tenant: {e}")
            # Don't fail the request, just log and continue without tenant

        try:
            response = await call_next(request)
            return response
        finally:
            # Clear context after request
            set_tenant_context(None)

    async def _resolve_tenant(self, request: Request, user_id: str) -> TenantContext | None:
        """Resolve tenant from request headers or user's primary tenant."""

        tenant = None
        tenant_id = None

        # 1. Try X-Tenant-ID header
        header_tenant_id = request.headers.get("X-Tenant-ID")
        if header_tenant_id:
            tenant = tenant_manager.get_tenant(header_tenant_id)
            if tenant:
                tenant_id = header_tenant_id

        # 2. Try X-Tenant-Slug header
        if not tenant:
            header_slug = request.headers.get("X-Tenant-Slug")
            if header_slug:
                tenant = tenant_manager.get_tenant_by_slug(header_slug)
                if tenant:
                    tenant_id = tenant.tenant_id

        # 3. Try subdomain (for custom domain support)
        if not tenant:
            host = request.headers.get("host", "")
            # Check if it's a subdomain (e.g., acme.vasignals.com)
            if host and "." in host:
                subdomain = host.split(".")[0]
                if subdomain not in ("www", "api", "dashboard"):
                    tenant = tenant_manager.get_tenant_by_slug(subdomain)
                    if tenant:
                        tenant_id = tenant.tenant_id

        # 4. Fall back to user's primary tenant
        if not tenant:
            user_tenants = tenant_manager.get_user_tenants(user_id)
            primary = next((t for t in user_tenants if t["is_primary"]), None)
            if primary:
                tenant = tenant_manager.get_tenant(primary["tenant_id"])
                tenant_id = primary["tenant_id"]

        if not tenant:
            # User has no tenants - might need to create one
            return None

        # Verify user is a member of this tenant
        user_role = tenant_manager.get_member_role(tenant_id, user_id)
        if not user_role:
            raise HTTPException(status_code=403, detail=f"Not a member of tenant {tenant.name}")

        # Get tenant settings
        settings = tenant_manager.get_tenant_settings(tenant_id)

        return TenantContext(
            tenant_id=tenant.tenant_id,
            tenant_name=tenant.name,
            tenant_slug=tenant.slug,
            plan=tenant.plan,
            user_id=user_id,
            user_role=user_role,
            settings=settings,
        )


def tenant_scoped_query(base_query: str, tenant_id: str, tenant_column: str = "tenant_id") -> str:
    """
    Add tenant scoping to a SQL query.

    Usage:
        query = tenant_scoped_query(
            "SELECT * FROM signals WHERE severity = :severity",
            tenant_context.tenant_id
        )
        # Returns: SELECT * FROM signals WHERE severity = :severity AND tenant_id = :tenant_id
    """
    # Simple approach - add AND clause
    # In production, use a more robust SQL parser
    if "WHERE" in base_query.upper():
        return f"{base_query} AND {tenant_column} = :tenant_id"
    else:
        return f"{base_query} WHERE {tenant_column} = :tenant_id"
