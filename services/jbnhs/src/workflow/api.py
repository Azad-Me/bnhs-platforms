from fastapi import APIRouter

from .review.api import router as review_router
from .submit.api import router as submit_router


router = APIRouter()
router.include_router(submit_router)
router.include_router(review_router)
