import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ....common.db.dependencies import get_db_session
from ....common.responses import ApiResponse, handle_api_exceptions
from ..schemas import GoogleSignInRequest, TokenResponse
from ..service import (
    AuthenticationService,
    GoogleIdentityConflictError,
    InvalidGoogleCredential,
    UserNotFoundError,
    create_access_token,
    verify_google_credential,
)
from ...router import _LOGIN_ERROR_RULE


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["user management"])


@router.post("/auth/login", response_model=ApiResponse[TokenResponse])
@handle_api_exceptions(
    {
        InvalidGoogleCredential: _LOGIN_ERROR_RULE,
        UserNotFoundError: _LOGIN_ERROR_RULE,
        GoogleIdentityConflictError: _LOGIN_ERROR_RULE,
    }
)
async def login(
    payload: GoogleSignInRequest,
    session: AsyncSession = Depends(get_db_session),
    user_management_service: AuthenticationService = Depends(AuthenticationService),
) -> ApiResponse[TokenResponse]:
    identity = await verify_google_credential(payload.credential)
    user = await user_management_service.authenticate_google_identity(session, identity)
    access_token, expires_in = create_access_token(user.id)
    logger.info("Google sign-in succeeded for user_id=%s", user.id)
    return ApiResponse.success(
        TokenResponse(access_token=access_token, expires_in=expires_in)
    )
