from fastapi import APIRouter

from .src.assignments import router as assignments_router
from .src.catalog.api import router as catalog_router
from .src.dashboard import router as dashboard_router
from .src.qc import router as qc_router
from .src.stitching import router as stitching_router
from .src.workflow import router as workflow_router


router = APIRouter()
router.include_router(catalog_router)
router.include_router(dashboard_router)
router.include_router(assignments_router)
router.include_router(qc_router)
router.include_router(stitching_router)
router.include_router(workflow_router)
