import os
import importlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from VPSBACKEND.database import init_db
from VPSBACKEND.utils.limiter import limiter

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s → %(message)s",
)
logger = logging.getLogger("VPSBACKEND")

ENV           = os.getenv("ENV", "development")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")
FRONTEND_URL  = os.getenv("FRONTEND_URL", "http://localhost:3000")
IS_PROD       = ENV == "production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 VPSBACKEND Starting...")
    logger.info(f"   ENV  → {ENV}")
    logger.info(f"   Docs → {'DISABLED' if IS_PROD else '/docs'}")

    init_db()
    logger.info("✅ Database ready.")

    _mount_auth_routers(app)
    logger.info("✅ Auth routers mounted.")

    autoload_endpoints(app)
    logger.info("✅ All endpoints loaded.")

    yield
    logger.info("🛑 VPSBACKEND Shutting down...")


app = FastAPI(
    title="VPSBACKEND",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None    if IS_PROD else "/docs",
    redoc_url=None   if IS_PROD else "/redoc",
    openapi_url=None if IS_PROD else "/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins    =[FRONTEND_URL] if IS_PROD else ["*"],
    allow_credentials=True,
    allow_methods    =["GET", "POST", "PUT", "DELETE"],
    allow_headers    =["Content-Type", "Authorization"],
)

if IS_PROD:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=ALLOWED_HOSTS,
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"]  = "nosniff"
    response.headers["X-Frame-Options"]          = "DENY"
    response.headers["X-XSS-Protection"]         = "1; mode=block"
    response.headers["Referrer-Policy"]          = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]       = "geolocation=(), microphone=()"
    if IS_PROD:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"]   = "default-src 'self'"
    response.headers.pop("server", None)
    response.headers.pop("x-powered-by", None)
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    ip = get_remote_address(request)
    logger.info(f"  {request.method} {request.url.path} ← {ip}")
    response = await call_next(request)
    logger.info(f"  → {response.status_code}")
    return response


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=404, content={"detail": "Not found"})


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "env": ENV}


# ─────────────────────────────────────────
# Auth Routers Mount
# ─────────────────────────────────────────

def _mount_auth_routers(app: FastAPI):
    # Email/password login
    try:
        from VPSBACKEND.Login import router as login_router
        app.include_router(login_router)
        logger.info("  ✅ Loaded → Login")
    except Exception as e:
        logger.error(f"  ❌ Failed → Login: {e}")

    # Registration
    try:
        from VPSBACKEND.Login.Registration import router as register_router
        app.include_router(register_router)
        logger.info("  ✅ Loaded → Registration")
    except Exception as e:
        logger.error(f"  ❌ Failed → Registration: {e}")

    # Google + GitHub OAuth
    try:
        from VPSBACKEND.Login.OAuth import router as oauth_router
        app.include_router(oauth_router)
        logger.info("  ✅ Loaded → OAuth (Google + GitHub)")
    except Exception as e:
        logger.error(f"  ❌ Failed → OAuth: {e}")


# ─────────────────────────────────────────
# Autoloader (endpoints/ folder)
# ─────────────────────────────────────────

def autoload_endpoints(app: FastAPI):
    base = os.path.join(os.path.dirname(__file__), "endpoints")
    for folder in os.listdir(base):
        folder_path = os.path.join(base, folder)
        if not os.path.isdir(folder_path):
            continue
        module_path = f"VPSBACKEND.endpoints.{folder}"
        try:
            module = importlib.import_module(module_path)
            if hasattr(module, "router"):
                app.include_router(module.router)
                logger.info(f"  ✅ Loaded → {folder}")
            else:
                logger.warning(f"  ⚠️  No router → {folder}")
        except Exception as e:
            logger.error(f"  ❌ Failed → {folder}: {e}")


if __name__ == "__main__":
    uvicorn.run(
        "VPSBACKEND.__main__:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=not IS_PROD,
        workers=int(os.getenv("WORKERS", 1)),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    
