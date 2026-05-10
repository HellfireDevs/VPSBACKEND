from fastapi import APIRouter
from .instances import router as instances_router
from .ami import router as ami_router
from .pricing import router as pricing_router
from .stock import router as stock_router

router = APIRouter()
router.include_router(instances_router)
router.include_router(ami_router)
router.include_router(pricing_router)
router.include_router(stock_router)
