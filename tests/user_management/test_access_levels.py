from __future__ import annotations

import unittest

from fastapi import HTTPException
from pydantic import ValidationError

from services.common.constant.access_level_enum import AccessLevel
from services.common.models import User
from services.user_management.router import require_admin
from services.user_management.schemas import UserCreate, UserUpdate


class AccessLevelSchemaTests(unittest.TestCase):
    def test_supported_access_levels(self):
        self.assertEqual(
            [level.value for level in AccessLevel],
            ["admin", "reviewer"],
        )

    def test_user_create_normalizes_and_validates_access_level(self):
        user = UserCreate(
            name="Volunteer",
            email="person@example.org",
            level=" REVIEWER ",
        )
        self.assertIs(user.level, AccessLevel.REVIEWER)

        with self.assertRaises(ValidationError):
            UserCreate(
                name="Volunteer",
                email="person@example.org",
                level="unknown",
            )

    def test_user_update_normalizes_and_validates_access_level(self):
        update = UserUpdate(level="ADMIN")
        self.assertIs(update.level, AccessLevel.ADMIN)

        with self.assertRaises(ValidationError):
            UserUpdate(level="unknown")


class AccessControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_admins_pass_admin_authorization(self):
        admin = User(
            name="Admin",
            email="admin@example.org",
            level=AccessLevel.ADMIN.value,
        )
        reviewer = User(
            name="Reviewer",
            email="reviewer@example.org",
            level=AccessLevel.REVIEWER.value,
        )

        self.assertIs(await require_admin(admin), admin)
        with self.assertRaises(HTTPException) as error:
            await require_admin(reviewer)
        self.assertEqual(error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
