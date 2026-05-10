import bcrypt
import asyncio

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import User
from VPSBACKEND.Login.Coockis import get_current_user
from VPSBACKEND.__main__ import limiter

router = APIRouter(prefix="/api/users", tags=["Users"])


# ─────────────────────────────────────────
# Get Profile
# ─────────────────────────────────────────

@router.get("/profile")
@limiter.limit("30/minute")
async def get_profile(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(404, "User not found")

    return {
        "id":             user.id,
        "email":          user.email,
        "role":           user.role,
        "is_verified":    user.is_verified,
        "is_suspended":   user.is_suspended,
        "suspend_reason": user.suspend_reason,
        "wallet_balance": user.wallet_balance,
        "ip_address":     user.ip_address,
        "created_at":     user.created_at,
        "updated_at":     user.updated_at,
    }


# ─────────────────────────────────────────
# Change Password
# ─────────────────────────────────────────

@router.put("/change-password")
@limiter.limit("5/hour")
async def change_password(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    body         = await request.json()
    old_password = body.get("old_password", "")
    new_password = body.get("new_password", "")

    # ── 1. Validate input ──
    if not old_password or not new_password:
        raise HTTPException(400, "Old and new password are required")

    if old_password == new_password:
        raise HTTPException(400, "New password must be different from old password")

    # ── 2. Password strength check ──
    strong, reason = _is_strong_password(new_password)
    if not strong:
        raise HTTPException(400, reason)

    # ── 3. Find user ──
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(404, "User not found")

    # ── 4. Verify old password ──
    if not bcrypt.checkpw(old_password.encode(), user.password_hash.encode()):
        raise HTTPException(401, "Current password is incorrect")

    # ── 5. Update password ──
    user.password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    db.commit()

    # ── 6. Send notification email (background) ──
    asyncio.create_task(
        _send_password_changed_email(user.email)
    )

    return {"message": "Password changed successfully"}


# ─────────────────────────────────────────
# Change Email
# ─────────────────────────────────────────

@router.put("/change-email")
@limiter.limit("3/hour")
async def change_email(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    body         = await request.json()
    new_email    = body.get("new_email", "").strip().lower()
    password     = body.get("password", "")

    # ── 1. Validate input ──
    if not new_email or not password:
        raise HTTPException(400, "New email and password are required")

    if not _is_valid_email(new_email):
        raise HTTPException(400, "Invalid email format")

    # ── 2. Find user ──
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(404, "User not found")

    # ── 3. Verify password ──
    if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        raise HTTPException(401, "Password is incorrect")

    # ── 4. Check email not already taken ──
    existing = db.query(User).filter(User.email == new_email).first()
    if existing:
        raise HTTPException(409, "This email is already in use")

    old_email = user.email

    # ── 5. Update email ──
    user.email       = new_email
    user.is_verified = False   # re-verification required
    db.commit()

    # ── 6. Notify both old and new email ──
    asyncio.create_task(
        _send_email_changed_notification(old_email, new_email)
    )

    return {"message": "Email updated successfully. Please verify your new email."}


# ─────────────────────────────────────────
# Delete Account
# ─────────────────────────────────────────

@router.delete("/delete-account")
@limiter.limit("2/day")
async def delete_account(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    body     = await request.json()
    password = body.get("password", "")

    if not password:
        raise HTTPException(400, "Password is required to delete account")

    # ── 1. Find user ──
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(404, "User not found")

    # ── 2. Verify password ──
    if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        raise HTTPException(401, "Password is incorrect")

    # ── 3. Check no active VPS ──
    from VPSBACKEND.Database.models import VPSOrder, VPSStatus
    active_vps = db.query(VPSOrder).filter(
        VPSOrder.user_id == user.id,
        VPSOrder.status  == VPSStatus.active,
    ).first()
    if active_vps:
        raise HTTPException(400, "Please delete all active VPS instances before deleting your account")

    email = user.email

    # ── 4. Delete user ──
    db.delete(user)
    db.commit()

    # ── 5. Notify ──
    asyncio.create_task(_send_account_deleted_email(email))

    return {"message": "Account deleted successfully"}


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def _is_strong_password(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        return False, "Password must contain at least one special character"
    return True, ""


def _is_valid_email(email: str) -> bool:
    import re
    return bool(re.match(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$", email))


# ─────────────────────────────────────────
# Background Email Tasks
# ─────────────────────────────────────────

async def _send_password_changed_email(email: str):
    from VPSBACKEND.Notification import send_password_changed_email
    await send_password_changed_email(email)


async def _send_email_changed_notification(old_email: str, new_email: str):
    from VPSBACKEND.Notification import send_email_changed_email
    await send_email_changed_email(old_email, new_email)


async def _send_account_deleted_email(email: str):
    from VPSBACKEND.Notification import send_account_deleted_email
    await send_account_deleted_email(email)
