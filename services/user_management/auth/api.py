from fastapi import APIRouter

from .current_user.api import router as current_user_router
from .login.api import router as login_router

router = APIRouter()
router.include_router(login_router)
router.include_router(current_user_router)
