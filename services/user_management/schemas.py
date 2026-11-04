from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from ..common.constant.access_level_enum import AccessLevel


def _clean_required_text(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("This field must not be blank.")
    return cleaned


def _normalize_access_level(value: object) -> AccessLevel:
    if isinstance(value, AccessLevel):
        return value
    if isinstance(value, str):
        try:
            return AccessLevel(value.strip().casefold())
        except ValueError as error:
            choices = ", ".join(level.value for level in AccessLevel)
            raise ValueError(
                f"Access level must be one of: {choices}."
            ) from error
    raise ValueError("Access level must be a string.")


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    level: AccessLevel

    @field_validator("name")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return _clean_required_text(value)

    @field_validator("level", mode="before")
    @classmethod
    def normalize_level(cls, value: object) -> AccessLevel:
        return _normalize_access_level(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    level: AccessLevel | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def clean_optional_name(cls, value: str | None) -> str | None:
        return _clean_required_text(value) if value is not None else None

    @field_validator("level", mode="before")
    @classmethod
    def normalize_level(cls, value: object) -> AccessLevel | None:
        if value is None or isinstance(value, AccessLevel):
            return value
        return _normalize_access_level(value)

    @field_validator("email")
    @classmethod
    def normalize_optional_email(cls, value: EmailStr | None) -> str | None:
        return str(value).strip().lower() if value is not None else None

    @model_validator(mode="after")
    def require_changes(self) -> UserUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Update fields must not be null.")
        return self


class GoogleSignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential: str = Field(min_length=1, max_length=8192)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    level: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
