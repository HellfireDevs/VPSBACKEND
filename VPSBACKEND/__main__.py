import os
import importlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import uvicorn

# ─────────────────────────────────────────
# Logging Setup
# ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s → %(message)s",
)
logger = logging.getLogger("VPSBACKEND")

# ─────────────────────────────────────────
# ENV
# ─────────────────────────────────────────
ENV         = os.getenv("ENV", "development")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")
FRONTEND_URL  = os.getenv("FRONTEND_URL", "http://localhost:3000")
IS_PROD       = ENV == "production"

# ─────────────────────────────────────────
# Rate Limiter (Global)
# ─────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute"],          # Global default
    storage_uri=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

# ─────────────────────────────────────────
# Endpoint Rate Limits (Import anywhere)
# ─────────────────────────────────────────
RATE_LIMITS = {
    "auth_login":       "5/minute",         # Brute force rokne ke liye
    "auth_register":    "3/minute",
    "auth_forgot":      "3/hour",
    "vps_create":       "5/hour",
    "vps_action":       "20/minute",        # start/stop/restart
    "port_open":        "10/minute",
    "payment_utr":      "5/hour",
    "support_ticket":   "5/hour",
    "appeal_submit":    "2/day",
    "pem_download":     "5/hour",
    "admin_broadcast":  "3/hour",
    "global_default":   "200/minute",
}

# ─────────────────────────────────────────
# Lifespan (Startup / Shutdown)
# ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 VPSBACKEND Starting...")
    logger.info(f"   ENV        → {ENV}")
    logger.info(f"   Docs       → {'DISABLED' if IS_PROD else '/docs'}")
    autoload_endpoints(app)
    logger.info("✅ All endpoints loaded.")
    yield
    logger.info("🛑 VPSBACKEND Shutting down...")

# ─────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────
app = FastAPI(
    title="VPSBACKEND",
    version="1.0.0",
    lifespan=lifespan,

    # Production mein docs bilkul band
    docs_url=None if IS_PROD else "/docs",
    redoc_url=None if IS_PROD else "/redoc",
    openapi_url=None if IS_PROD else "/openapi.json",
)

# ─────────────────────────────────────────
# Rate Limiter Middleware
# ─────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ─────────────────────────────────────────
# CORS
# ─────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL] if IS_PROD else ["*"],
    allow_credentials=True,                 # Cookies ke liye
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# ─────────────────────────────────────────
# Trusted Hosts (Production mein)
# ─────────────────────────────────────────
if IS_PROD:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=ALLOWED_HOSTS,
    )

# ─────────────────────────────────────────
# Security Headers Middleware
# ─────────────────────────────────────────
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)

    # Inspector/Console mein API details hide karne ke liye
    response.headers["X-Content-Type-Options"]    = "nosniff"
    response.headers["X-Frame-Options"]            = "DENY"
    response.headers["X-XSS-Protection"]           = "1; mode=block"
    response.headers["Referrer-Policy"]            = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]         = "geolocation=(), microphone=()"

    if IS_PROD:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"]   = "default-src 'self'"

    # Server header hatao (version leak na ho)
    response.headers.pop("server", None)
    response.headers.pop("x-powered-by", None)

    return response

# ─────────────────────────────────────────
# IP Logging Middleware (Debug)
# ─────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    ip = get_remote_address(request)
    logger.info(f"  {request.method} {request.url.path} ← {ip}")
    response = await call_next(request)
    logger.info(f"  → {response.status_code}")
    return response

# ─────────────────────────────────────────
# Global Error Handler
# ─────────────────────────────────────────
@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},  # Stack trace hide karo
    )

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=404,
        content={"detail": "Not found"},
    )

# ─────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "env": ENV}

# ─────────────────────────────────────────
# Autoloader — Har endpoint ka Blueprint load karo
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
                logger.info(f"  ✅ Loaded endpoint → {folder}")
            else:
                logger.warning(f"  ⚠️  No router found in → {folder}")
        except Exception as e:
            logger.error(f"  ❌ Failed to load → {folder}: {e}")

# ─────────────────────────────────────────
# Run
# ─────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "VPSBACKEND.__main__:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=not IS_PROD,
        workers=int(os.getenv("WORKERS", 1)),
        proxy_headers=True,                 # Nginx ke peeche ho toh
        forwarded_allow_ips="*",
  )
  
