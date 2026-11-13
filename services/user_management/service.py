"""Compatibility exports for the user administration service."""

from .admin.service import (
    GoogleIdentityConflictError,
    LastActiveAdminError,
    UserEmailConflictError,
    UserManagementService,
    UserNotFoundError,
)

user_management_service = UserManagementService()

__all__ = [
    "GoogleIdentityConflictError",
    "LastActiveAdminError",
    "UserEmailConflictError",
    "UserManagementService",
    "UserNotFoundError",
    "user_management_service",
]
