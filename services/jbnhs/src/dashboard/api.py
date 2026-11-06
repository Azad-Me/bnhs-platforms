from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ....common.db.dependencies import get_db_session
from ....common.models import User
from ....common.responses import API_ERROR_RESPONSES, ApiResponse
from ....user_management.router import get_current_user
from .schemas import DashboardSummary
from .service import get_dashboard_summary


router = APIRouter(
    prefix="/api",
    tags=["dashboard"],
    responses=API_ERROR_RESPONSES,
)


@router.get(
    "/dashboard/progress",
    response_model=ApiResponse[DashboardSummary],
)
async def read_dashboard_progress(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> ApiResponse[DashboardSummary]:
    return ApiResponse.success(await get_dashboard_summary(session))
