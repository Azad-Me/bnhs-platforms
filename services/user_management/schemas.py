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

from .validators import clean_required_text, normalize_role_key


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    level: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)

    @field_validator("name")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return clean_required_text(value)

    @field_validator("level", mode="before")
    @classmethod
    def normalize_level(cls, value: object) -> str:
        return normalize_role_key(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    level: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_]*$", max_length=64
    )
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def clean_optional_name(cls, value: str | None) -> str | None:
        return clean_required_text(value) if value is not None else None

    @field_validator("level", mode="before")
    @classmethod
    def normalize_level(cls, value: object) -> str | None:
        if value is None:
            return value
        return normalize_role_key(value)

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
