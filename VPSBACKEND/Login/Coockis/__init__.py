import jwt
import os
from datetime import datetime, timedelta
from fastapi import Request, HTTPException
from fastapi.responses import Response

SECRET      = os.getenv("JWT_SECRET", "change-this-in-production")
ALGORITHM   = "HS256"
EXPIRE_DAYS = 7


# ─────────────────────────────────────────
# Create Token
# ─────────────────────────────────────────

def create_token(data: dict) -> str:
    payload = {
        **data,
        "exp": datetime.utcnow() + timedelta(days=EXPIRE_DAYS),
        "iat": datetime.utcnow(),  # issued at
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


# ─────────────────────────────────────────
# Set Cookie
# ─────────────────────────────────────────

def set_cookie(response: Response, token: str):
    response.set_cookie(
        key      = "access_token",
        value    = token,
        httponly = True,                    # JS cannot access it
        secure   = True,                    # HTTPS only
        samesite = "strict",                # CSRF protection
        max_age  = 60 * 60 * 24 * EXPIRE_DAYS,
    )


# ─────────────────────────────────────────
# Clear Cookie (Logout)
# ─────────────────────────────────────────

def clear_cookie(response: Response):
    response.delete_cookie(
        key      = "access_token",
        httponly = True,
        secure   = True,
        samesite = "strict",
    )


# ─────────────────────────────────────────
# Decode Token
# ─────────────────────────────────────────

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired, please login again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid session, please login again")


# ─────────────────────────────────────────
# Dependencies (use in endpoints)
# ─────────────────────────────────────────

def get_current_user(request: Request) -> dict:
    """
    Use this in any endpoint:
    user = Depends(get_current_user)
    Returns: { user_id, role, exp, iat }
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(401, "Authentication required")
    return decode_token(token)


def require_admin(request: Request) -> dict:
    """
    Use this in admin-only endpoints:
    user = Depends(require_admin)
    """
    user = get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    return user
