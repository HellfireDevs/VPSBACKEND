from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import User, Appeal, AppealStatus
from VPSBACKEND.Login.Coockis import get_current_user
from VPSBACKEND.utils.limiter import limiter

router = APIRouter(tags=["Suspend & Appeal"])


# ─────────────────────────────────────────
# GET /api/suspend/status
# ─────────────────────────────────────────

@router.get("/api/suspend/status")
async def suspend_status(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(404, "User not found")

    if not user.is_suspended:
        return {
            "is_suspended": False,
            "message":      "Your account is in good standing",
        }

    # Appeal ka current status bhi bhejo
    appeal = db.query(Appeal).filter(
        Appeal.user_id == user.id
    ).order_by(Appeal.created_at.desc()).first()

    return {
        "is_suspended":   True,
        "suspend_reason": user.suspend_reason or "No reason provided",
        "appeal": {
            "submitted":   appeal is not None,
            "status":      appeal.status       if appeal else None,
            "admin_note":  appeal.admin_note   if appeal else None,
            "created_at":  appeal.created_at   if appeal else None,
            "reviewed_at": appeal.reviewed_at  if appeal else None,
        },
    }


# ─────────────────────────────────────────
# POST /api/appeal/submit
# ─────────────────────────────────────────

@router.post("/api/appeal/submit")
@limiter.limit("3/day")
async def submit_appeal(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    body   = await request.json()
    reason = body.get("reason", "").strip()

    if not reason:
        raise HTTPException(400, "Reason is required")
    if len(reason) < 30:
        raise HTTPException(400, "Reason too short (min 30 characters). Please explain in detail")
    if len(reason) > 2000:
        raise HTTPException(400, "Reason too long (max 2000 characters)")

    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(404, "User not found")

    if not user.is_suspended:
        raise HTTPException(400, "Your account is not suspended")

    # Pending appeal pehle se hai?
    existing = db.query(Appeal).filter(
        Appeal.user_id == user.id,
        Appeal.status  == AppealStatus.pending,
    ).first()
    if existing:
        raise HTTPException(409, "You already have a pending appeal. Please wait for admin review")

    # Approved appeal pehle se hai?
    approved = db.query(Appeal).filter(
        Appeal.user_id == user.id,
        Appeal.status  == AppealStatus.approved,
    ).first()
    if approved:
        raise HTTPException(400, "Your previous appeal was approved. Please contact support if issue persists")

    appeal = Appeal(
        user_id = user.id,
        reason  = reason,
        status  = AppealStatus.pending,
    )
    db.add(appeal)
    db.commit()
    db.refresh(appeal)

    # Admin ko email
    try:
        import os
        from VPSBACKEND.Notification import _send
        admin_email  = os.getenv("ADMIN_EMAIL")
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        if admin_email:
            _send(
                admin_email,
                f"⚠️ New Suspend Appeal — {user.email} | VPS Store",
                f"""
                <body style="font-family:Arial,sans-serif;padding:32px;background:#f4f4f4;">
                  <table width="600" style="background:#fff;border-radius:6px;
                         border:1px solid #ddd;padding:32px;margin:auto;">
                    <tr><td>
                      <h2 style="color:#1a1a2e;margin-top:0;">New Suspend Appeal</h2>
                      <p><b>User:</b> {user.email}</p>
                      <p><b>Appeal ID:</b> #{appeal.id}</p>
                      <p><b>Reason:</b></p>
                      <blockquote style="border-left:3px solid #ccc;padding-left:16px;color:#555;margin:0;">
                        {reason}
                      </blockquote>
                      <a href="{frontend_url}/admin/appeals"
                         style="display:inline-block;background:#1a1a2e;color:#fff;
                                padding:12px 24px;border-radius:4px;
                                text-decoration:none;margin-top:24px;font-size:14px;">
                        Review Appeal →
                      </a>
                    </td></tr>
                  </table>
                </body>
                """
            )
    except Exception:
        pass  # Email fail ho toh appeal block mat karo

    return {
        "message":    "Appeal submitted. Admin will review within 24-48 hours",
        "appeal_id":  appeal.id,
        "status":     appeal.status,
        "created_at": appeal.created_at,
    }


# ─────────────────────────────────────────
# GET /api/appeal/status
# ─────────────────────────────────────────

@router.get("/api/appeal/status")
async def appeal_status(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    appeal = db.query(Appeal).filter(
        Appeal.user_id == current_user["user_id"]
    ).order_by(Appeal.created_at.desc()).first()

    if not appeal:
        return {
            "has_appeal": False,
            "message":    "No appeal found",
        }

    return {
        "has_appeal":  True,
        "appeal_id":   appeal.id,
        "status":      appeal.status,
        "reason":      appeal.reason,
        "admin_note":  appeal.admin_note,
        "created_at":  appeal.created_at,
        "reviewed_at": appeal.reviewed_at,
      }
  
