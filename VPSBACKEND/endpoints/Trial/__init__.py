import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import (
    Trial, VPSOrder, VPSStatus,
    AWSAccount, AWSAccountType, User,
)
from VPSBACKEND.Login.Coockis import get_current_user
from VPSBACKEND.utils.limiter import limiter
from VPSBACKEND.utils.tasks import launch_vps_task

router = APIRouter(prefix="/api/trial", tags=["Trial"])

TRIAL_DAYS          = 7
TRIAL_INSTANCE_TYPE = os.getenv("TRIAL_INSTANCE_TYPE", "t3.micro")
TRIAL_AMI_ID        = os.getenv("TRIAL_AMI_ID", "ami-0f5ee92e2d63afc18")   # Ubuntu 22.04 ap-south-1
TRIAL_STORAGE_GB    = 20
TRIAL_REGION        = os.getenv("AWS_REGION", "ap-south-1")


# ─────────────────────────────────────────
# POST /api/trial/start
# ─────────────────────────────────────────

@router.post("/start")
@limiter.limit("3/hour")
async def start_trial(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    ip      = request.client.host

    # ── 1. User fetch + suspend check ──
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    if user.is_suspended:
        reason = user.suspend_reason or "No reason provided"
        raise HTTPException(403, f"Account suspended: {reason}")

    # ── 2. User already trial le chuka hai? ──
    existing_trial = db.query(Trial).filter(Trial.user_id == user_id).first()
    if existing_trial:
        raise HTTPException(409, "You have already used your free trial")

    # ── 3. Is IP se pehle koi trial hua hai? ──
    ip_trial = db.query(Trial).filter(Trial.ip_address == ip).first()
    if ip_trial:
        raise HTTPException(409, "A trial has already been used from this IP address")

    # ── 4. Trial AWS account dhundo ──
    aws_account = db.query(AWSAccount).filter(
        AWSAccount.type      == AWSAccountType.trial,
        AWSAccount.is_active == True,
    ).order_by(AWSAccount.used_credits).first()

    if not aws_account:
        raise HTTPException(503, "Trial is not available at the moment. Please try again later")

    if aws_account.remaining_credits <= 0:
        raise HTTPException(503, "Trial credits exhausted. Please contact support")

    # ── 5. VPS record banao (pending) ──
    server_name = f"Trial-{user_id}"
    expires_at  = datetime.utcnow() + timedelta(days=TRIAL_DAYS)

    vps = VPSOrder(
        user_id        = user_id,
        aws_account_id = aws_account.id,
        instance_type  = TRIAL_INSTANCE_TYPE,
        ami_id         = TRIAL_AMI_ID,
        os             = "Ubuntu 22.04",
        region         = TRIAL_REGION,
        storage_gb     = TRIAL_STORAGE_GB,
        server_name    = server_name,
        status         = VPSStatus.pending,
        expires_at     = expires_at,
    )
    db.add(vps)
    db.commit()
    db.refresh(vps)

    # ── 6. Trial record banao ──
    trial = Trial(
        user_id        = user_id,
        ip_address     = ip,
        aws_account_id = aws_account.id,
        started_at     = datetime.utcnow(),
        expires_at     = expires_at,
        is_used        = True,
    )
    db.add(trial)
    db.commit()

    # ── 7. Celery se background launch ──
    launch_vps_task.delay(
        vps_id         = vps.id,
        user_id        = user_id,
        aws_account_id = aws_account.id,
        config         = {
            "instance_type": TRIAL_INSTANCE_TYPE,
            "ami_id":        TRIAL_AMI_ID,
            "os":            "Ubuntu 22.04",
            "storage_gb":    TRIAL_STORAGE_GB,
            "server_name":   server_name,
            "region":        TRIAL_REGION,
        },
    )

    return {
        "message":    "Trial started! Your VPS is being set up.",
        "vps_id":     vps.id,
        "status":     "pending",
        "expires_at": expires_at,
        "info":       f"VPS ready hone mein ~2-3 minutes lagte hain. Track karo: /api/vps/{vps.id}/status",
    }


# ─────────────────────────────────────────
# GET /api/trial/status
# ─────────────────────────────────────────

@router.get("/status")
async def trial_status(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    user_id = current_user["user_id"]

    trial = db.query(Trial).filter(Trial.user_id == user_id).first()

    # ── Trial nahi liya abhi tak ──
    if not trial:
        return {
            "has_trial":   False,
            "message":     "You have not started a trial yet",
        }

    # ── Trial VPS dhundo ──
    vps = db.query(VPSOrder).filter(
        VPSOrder.user_id        == user_id,
        VPSOrder.aws_account_id == trial.aws_account_id,
        VPSOrder.server_name.like("Trial-%"),
    ).order_by(VPSOrder.created_at.desc()).first()

    now         = datetime.utcnow()
    is_expired  = now > trial.expires_at
    days_left   = max(0, (trial.expires_at - now).days)
    hours_left  = max(0, int((trial.expires_at - now).total_seconds() / 3600))

    return {
        "has_trial":    True,
        "is_expired":   is_expired,
        "started_at":   trial.started_at,
        "expires_at":   trial.expires_at,
        "days_left":    days_left,
        "hours_left":   hours_left,
        "vps": {
            "id":           vps.id           if vps else None,
            "status":       vps.status       if vps else None,
            "elastic_ip":   vps.elastic_ip   if vps else None,
            "instance_type": vps.instance_type if vps else TRIAL_INSTANCE_TYPE,
            "os":           vps.os           if vps else "Ubuntu 22.04",
        } if vps else None,
    }
