"""Compatibility exports for role administration."""

from .admin.role_service import RoleNotFoundError, RoleService

__all__ = ["RoleNotFoundError", "RoleService"]
