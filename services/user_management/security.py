from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token
import jwt

from ..common.env import load_environment


@dataclass(frozen=True)
class AuthSettings:
    secret_key: str
    token_expire_minutes: int
    issuer: str
    google_client_id: str


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    name: str


class AuthConfigurationError(RuntimeError):
    pass


class InvalidGoogleCredential(ValueError):
    pass


def load_auth_settings() -> AuthSettings:
    environment = load_environment()
    secret_key = environment.get("JWT_SECRET_KEY", "")
    if len(secret_key) < 32:
        raise AuthConfigurationError(
            "JWT_SECRET_KEY must be configured with at least 32 characters."
        )

    try:
        token_expire_minutes = int(
            environment.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
        )
    except ValueError as error:
        raise AuthConfigurationError(
            "JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be a positive integer."
        ) from error
    if token_expire_minutes <= 0:
        raise AuthConfigurationError(
            "JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be a positive integer."
        )

    issuer = environment.get("JWT_ISSUER", "bnhs-platforms").strip()
    if not issuer:
        raise AuthConfigurationError("JWT_ISSUER must not be blank.")
    google_client_id = environment.get("GOOGLE_CLIENT_ID", "").strip()
    if not google_client_id:
        raise AuthConfigurationError("GOOGLE_CLIENT_ID must be configured.")

    return AuthSettings(
        secret_key=secret_key,
        token_expire_minutes=token_expire_minutes,
        issuer=issuer,
        google_client_id=google_client_id,
    )


def _verify_google_credential(credential: str) -> GoogleIdentity:
    settings = load_auth_settings()
    try:
        claims = id_token.verify_oauth2_token(
            credential,
            GoogleAuthRequest(),
            audience=settings.google_client_id,
        )
    except (ValueError, google.auth.exceptions.GoogleAuthError) as error:
        raise InvalidGoogleCredential("Google credential verification failed.") from error

    subject = claims.get("sub")
    email = claims.get("email")
    email_verified = claims.get("email_verified")
    name = claims.get("name", "")
    if (
        not isinstance(subject, str)
        or not subject
        or not isinstance(email, str)
        or not email.strip()
        or email_verified not in (True, "true")
        or not isinstance(name, str)
    ):
        raise InvalidGoogleCredential("Google identity claims are incomplete.")

    return GoogleIdentity(
        subject=subject,
        email=email.strip().lower(),
        name=name.strip(),
    )


async def verify_google_credential(credential: str) -> GoogleIdentity:
    return await asyncio.to_thread(_verify_google_credential, credential)


def create_access_token(user_id: int) -> tuple[str, int]:
    settings = load_auth_settings()
    expires_in = settings.token_expire_minutes * 60
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "iss": settings.issuer,
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
        },
        settings.secret_key,
        algorithm="HS256",
    )
    return token, expires_in


def decode_access_token(token: str) -> int:
    settings = load_auth_settings()
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=["HS256"],
        issuer=settings.issuer,
        options={"require": ["exp", "iat", "iss", "sub"]},
    )
    subject = payload["sub"]
    if not isinstance(subject, str) or not subject.isdecimal():
        raise jwt.InvalidTokenError("Token subject must be a numeric user ID.")
    return int(subject)
