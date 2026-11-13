"""Schemas used by authentication routes."""

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import UserRead


class GoogleSignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential: str = Field(min_length=1, max_length=8192)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

__all__ = ["GoogleSignInRequest", "TokenResponse", "UserRead"]
