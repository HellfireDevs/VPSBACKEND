from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import User
from VPSBACKEND.Login.Coockis import get_current_user
from VPSBACKEND.__main__ import limiter
import os

router = APIRouter(tags=["Global"])

ENV = os.getenv("ENV", "development")


# ─────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────

@router.get("/health")
async def health(db: Session = Depends(get_db)):
    # Check DB connection too
    try:
        db.execute("SELECT 1")
        db_status = "connected"
    except Exception:
        db_status = "error"

    return {
        "status":   "ok",
        "env":      ENV,
        "database": db_status,
    }


# ─────────────────────────────────────────
# Me — Current Logged In User
# ─────────────────────────────────────────

@router.get("/api/auth/me")
@limiter.limit("30/minute")
async def me(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(404, "User not found")

    return {
        "id":             user.id,
        "email":          user.email,
        "role":           user.role,
        "is_verified":    user.is_verified,
        "is_suspended":   user.is_suspended,
        "wallet_balance": user.wallet_balance,
        "created_at":     user.created_at,
    }
