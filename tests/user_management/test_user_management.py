from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import jwt
from pydantic import ValidationError

from services.common.models import User
from services.user_management.schemas import GoogleSignInRequest, UserCreate, UserUpdate
from services.user_management.security import (
    GoogleIdentity,
    InvalidGoogleCredential,
    create_access_token,
    decode_access_token,
    verify_google_credential,
)
from services.user_management.service import (
    UserEmailConflictError,
    UserManagementService,
    UserNotFoundError,
)


class UserSchemaTests(unittest.TestCase):
    def test_create_normalizes_email_and_rejects_password_field(self):
        user = UserCreate(
            name=" Volunteer ",
            email="Person@Example.org",
            level="reviewer",
        )
        self.assertEqual(user.name, "Volunteer")
        self.assertEqual(user.email, "person@example.org")
        with self.assertRaises(ValidationError):
            UserCreate(
                name="Volunteer",
                email="person@example.org",
                level="reviewer",
                password="not-allowed",
            )

    def test_google_sign_in_requires_credential(self):
        self.assertEqual(
            GoogleSignInRequest(credential="google-id-token").credential,
            "google-id-token",
        )
        with self.assertRaises(ValidationError):
            GoogleSignInRequest(credential="")

    def test_update_requires_non_null_changes(self):
        with self.assertRaises(ValidationError):
            UserUpdate()
        with self.assertRaises(ValidationError):
            UserUpdate(name=None)
        self.assertFalse(UserUpdate(is_active=False).is_active)


class TokenTests(unittest.TestCase):
    def test_access_token_round_trip_and_expiration_config(self):
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": "test-secret-key-with-at-least-32-characters",
                "JWT_ACCESS_TOKEN_EXPIRE_MINUTES": "10",
                "JWT_ISSUER": "test",
                "GOOGLE_CLIENT_ID": "google-client-id",
            },
            clear=False,
        ):
            token, expires_in = create_access_token(1001)
            self.assertEqual(expires_in, 600)
            self.assertEqual(decode_access_token(token), 1001)

    def test_token_rejects_invalid_token(self):
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": "test-secret-key-with-at-least-32-characters",
                "JWT_ISSUER": "test",
                "GOOGLE_CLIENT_ID": "google-client-id",
            },
            clear=False,
        ):
            with self.assertRaises(jwt.InvalidTokenError):
                decode_access_token("not-a-token")


class GoogleCredentialTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_google_claims_become_identity(self):
        claims = {
            "sub": "google-subject",
            "email": "Person@Example.org",
            "email_verified": True,
            "name": "Google Name",
        }
        with (
            patch.dict(
                os.environ,
                {
                    "JWT_SECRET_KEY": "test-secret-key-with-at-least-32-characters",
                    "GOOGLE_CLIENT_ID": "expected-client-id",
                },
                clear=False,
            ),
            patch(
                "services.user_management.security.id_token.verify_oauth2_token",
                return_value=claims,
            ) as verify,
        ):
            identity = await verify_google_credential("google-id-token")

        self.assertEqual(
            identity,
            GoogleIdentity(
                subject="google-subject",
                email="person@example.org",
                name="Google Name",
            ),
        )
        self.assertEqual(verify.call_args.kwargs["audience"], "expected-client-id")

    async def test_unverified_google_email_is_rejected(self):
        with (
            patch.dict(
                os.environ,
                {
                    "JWT_SECRET_KEY": "test-secret-key-with-at-least-32-characters",
                    "GOOGLE_CLIENT_ID": "expected-client-id",
                },
                clear=False,
            ),
            patch(
                "services.user_management.security.id_token.verify_oauth2_token",
                return_value={
                    "sub": "google-subject",
                    "email": "person@example.org",
                    "email_verified": False,
                },
            ),
        ):
            with self.assertRaises(InvalidGoogleCredential):
                await verify_google_credential("google-id-token")


class UserServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_user_does_not_store_a_password(self):
        class FakeSession:
            added = None

            async def scalar(self, statement):
                return None

            def add(self, user):
                self.added = user

            async def flush(self):
                return None

        session = FakeSession()
        payload = UserCreate(
            name="Volunteer",
            email="person@example.org",
            level="reviewer",
        )
        user = await UserManagementService().create_user(session, payload)

        self.assertIs(user, session.added)
        self.assertFalse(hasattr(user, "password_hash"))

    async def test_create_user_rejects_duplicate_email(self):
        class FakeSession:
            async def scalar(self, statement):
                return 1001

        payload = UserCreate(
            name="Volunteer",
            email="person@example.org",
            level="reviewer",
        )
        with self.assertRaises(UserEmailConflictError):
            await UserManagementService().create_user(FakeSession(), payload)

    async def test_google_identity_binds_to_preprovisioned_user_by_email(self):
        user = User(
            name="Volunteer",
            email="person@example.org",
            level="reviewer",
            is_active=True,
        )

        class FakeSession:
            async def scalar(self, statement):
                return user

        result = await UserManagementService().authenticate_google_identity(
            FakeSession(),
            GoogleIdentity(
                subject="google-subject",
                email="person@example.org",
                name="Google Name",
            ),
        )
        self.assertIs(result, user)

    async def test_google_identity_requires_preprovisioned_user(self):
        class FakeSession:
            async def scalar(self, statement):
                return None

        with self.assertRaises(UserNotFoundError):
            await UserManagementService().authenticate_google_identity(
                FakeSession(),
                GoogleIdentity(
                    subject="google-subject",
                    email="unknown@example.org",
                    name="Unknown",
                ),
            )


if __name__ == "__main__":
    unittest.main()
