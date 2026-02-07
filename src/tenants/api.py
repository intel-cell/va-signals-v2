"""
Tenant management API endpoints.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth.middleware import require_auth, require_role
from ..auth.models import AuthContext, UserRole
from ..auth.rbac import RoleChecker
from .manager import tenant_manager
from .middleware import get_tenant_context
from .models import (
    TenantCreateRequest,
    TenantInviteRequest,
    TenantMemberResponse,
    TenantResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tenants", tags=["Tenants"])


@router.post("", response_model=TenantResponse)
async def create_tenant(
    request: TenantCreateRequest,
    current_user: AuthContext = Depends(require_auth),
):
    """
    Create a new tenant organization.

    The creating user becomes the owner with COMMANDER role.
    """
    user_id = current_user.user_id

    try:
        tenant = tenant_manager.create_tenant(request, user_id)
        members = tenant_manager.get_tenant_members(tenant.tenant_id)

        return TenantResponse(
            tenant_id=tenant.tenant_id,
            name=tenant.name,
            slug=tenant.slug,
            plan=tenant.plan.value,
            status=tenant.status.value,
            created_at=tenant.created_at.isoformat(),
            member_count=len(members),
        )
    except Exception as e:
        logger.error(f"Failed to create tenant: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me", summary="Get user's tenants")
async def get_my_tenants(
    current_user: AuthContext = Depends(require_auth),
):
    """Get all tenants the current user belongs to."""
    user_id = current_user.user_id
    tenants = tenant_manager.get_user_tenants(user_id)
    return {"tenants": tenants, "count": len(tenants)}


@router.get("/current", summary="Get current tenant context")
async def get_current_tenant():
    """Get the current tenant context for this request."""
    context = get_tenant_context()
    if not context:
        raise HTTPException(status_code=400, detail="No tenant context")

    return {
        "tenant_id": context.tenant_id,
        "tenant_name": context.tenant_name,
        "tenant_slug": context.tenant_slug,
        "plan": context.plan.value,
        "user_role": context.user_role,
    }


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    current_user=Depends(RoleChecker(UserRole.VIEWER)),
):
    """Get tenant details by ID."""
    tenant = tenant_manager.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    members = tenant_manager.get_tenant_members(tenant_id)

    return TenantResponse(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        slug=tenant.slug,
        plan=tenant.plan.value,
        status=tenant.status.value,
        created_at=tenant.created_at.isoformat(),
        member_count=len(members),
        owner_email=None,  # Would look up from users table
    )


@router.get("/{tenant_id}/settings", summary="Get tenant settings")
async def get_tenant_settings(
    tenant_id: str,
    current_user=Depends(RoleChecker(UserRole.LEADERSHIP)),
):
    """Get tenant settings. Requires LEADERSHIP role."""
    settings = tenant_manager.get_tenant_settings(tenant_id)
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    return settings.model_dump()


@router.get("/{tenant_id}/members", summary="List tenant members")
async def list_tenant_members(
    tenant_id: str,
    current_user=Depends(RoleChecker(UserRole.ANALYST)),
):
    """List all members of a tenant. Requires ANALYST role."""
    members = tenant_manager.get_tenant_members(tenant_id)
    return {
        "members": [
            TenantMemberResponse(
                user_id=m["user_id"],
                email=m["email"],
                display_name=m["display_name"],
                role=m["role"],
                joined_at=m["joined_at"],
                is_primary=m["is_primary"],
            )
            for m in members
        ],
        "count": len(members),
    }


@router.post("/{tenant_id}/members", summary="Invite a member")
async def invite_member(
    tenant_id: str,
    request: TenantInviteRequest,
    current_user: AuthContext = Depends(require_role(UserRole.LEADERSHIP, UserRole.COMMANDER)),
):
    """
    Invite a user to the tenant. Requires LEADERSHIP role.

    If the user doesn't exist, an invitation email will be sent.
    """
    # Check tenant exists
    tenant = tenant_manager.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Check settings for max users
    settings = tenant_manager.get_tenant_settings(tenant_id)
    members = tenant_manager.get_tenant_members(tenant_id)

    if settings and len(members) >= settings.max_users:
        raise HTTPException(
            status_code=400,
            detail=f"Tenant has reached maximum users ({settings.max_users}). Upgrade plan to add more.",
        )

    # In real implementation:
    # 1. Look up user by email or create pending invitation
    # 2. Send invitation email
    # 3. Add to tenant_members when accepted

    # For now, assume user exists
    user_id = f"user_{request.email.split('@')[0]}"

    try:
        member = tenant_manager.add_member(
            tenant_id=tenant_id,
            user_id=user_id,
            role=request.role,
            invited_by=current_user.user_id,
        )

        return {
            "success": True,
            "message": f"Invited {request.email} to {tenant.name}",
            "user_id": member.user_id,
            "role": member.role,
        }
    except Exception as e:
        logger.error(f"Failed to invite member: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{tenant_id}/members/{user_id}", summary="Remove a member")
async def remove_member(
    tenant_id: str,
    user_id: str,
    current_user=Depends(RoleChecker(UserRole.COMMANDER)),
):
    """Remove a user from the tenant. Requires COMMANDER role."""
    removed = tenant_manager.remove_member(tenant_id, user_id)

    if not removed:
        raise HTTPException(
            status_code=400, detail="Cannot remove user (not found or is primary owner)"
        )

    return {"success": True, "message": f"Removed user {user_id} from tenant"}


@router.patch("/{tenant_id}/members/{user_id}/role", summary="Update member role")
async def update_member_role(
    tenant_id: str,
    user_id: str,
    role: str = Query(..., description="New role for the user"),
    current_user=Depends(RoleChecker(UserRole.COMMANDER)),
):
    """Update a member's role. Requires COMMANDER role."""
    valid_roles = ["commander", "leadership", "analyst", "viewer"]
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")

    updated = tenant_manager.update_member_role(tenant_id, user_id, role)

    if not updated:
        raise HTTPException(status_code=404, detail="Member not found")

    return {"success": True, "message": f"Updated role to {role}"}
