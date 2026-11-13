from fastapi import APIRouter

from .pages.api import router as pages_router
from .revisions.api import router as revisions_router


router = APIRouter()
router.include_router(pages_router)
router.include_router(revisions_router)
