from fastapi import APIRouter, Depends

from ....common.models import User
from ....common.responses import API_ERROR_RESPONSES, ApiResponse
from ..schemas import UserRead
from ...router import get_current_user


router = APIRouter(
    prefix="/api",
    tags=["user management"],
    responses=API_ERROR_RESPONSES,
    dependencies=[Depends(get_current_user)],
)


@router.get("/auth/me", response_model=ApiResponse[UserRead])
async def read_current_user(
    user: User = Depends(get_current_user),
) -> ApiResponse[UserRead]:
    return ApiResponse.success(UserRead.model_validate(user))
