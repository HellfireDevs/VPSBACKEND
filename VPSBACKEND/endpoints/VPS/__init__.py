from fastapi import APIRouter
from .create  import router as create_router
from .control import router as control_router
from .delete  import router as delete_router
from .status  import router as status_router
from .usage   import router as usage_router
from .pem     import router as pem_router
from .ports   import router as ports_router
from .days    import router as days_router

router = APIRouter()
router.include_router(create_router)
router.include_router(control_router)
router.include_router(delete_router)
router.include_router(status_router)
router.include_router(usage_router)
router.include_router(pem_router)
router.include_router(ports_router)
router.include_router(days_router)
