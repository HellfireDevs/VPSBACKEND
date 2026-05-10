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

TRIAL_DAYS       = 7
TRIAL_STORAGE_GB = 20                                  # Fixed — user change nahi kar sakta
TRIAL_REGION     = os.getenv("AWS_REGION", "ap-south-1")

# ── Trial ke liye allowed instance types ──
TRIAL_ALLOWED_INSTANCES = {
    "t3.micro":  {"vcpu": 2,  "ram_gb": 1.0},
    "t3.small":  {"vcpu": 2,  "ram_gb": 2.0},
    "t3.medium": {"vcpu": 2,  "ram_gb": 4.0},
}

# ── Trial ke liye allowed OS + AMI map ──
TRIAL_ALLOWED_OS = {
    "ubuntu-22.04": {
        "label":  "Ubuntu 22.04 LTS",
        "ami_id": os.getenv("TRIAL_AMI_UBUNTU_22", "ami-0f5ee92e2d63afc18"),
    },
    "ubuntu-20.04": {
        "label":  "Ubuntu 20.04 LTS",
        "ami_id": os.getenv("TRIAL_AMI_UBUNTU_20", "ami-0851b76e8b1bce90b"),
    },
    "debian-12": {
        "label":  "Debian 12 Bookworm",
        "ami_id": os.getenv("TRIAL_AMI_DEBIAN_12", "ami-0376ac2f3a33daa01"),
    },
}


# ─────────────────────────────────────────
# GET /api/trial/options
# Frontend ke liye — kya-kya choose kar sakte hain
# ─────────────────────────────────────────

@router.get("/options")
async def trial_options():
    return {
        "instance_types": [
            {
                "value": k,
                "vcpu":  v["vcpu"],
                "ram_gb": v["ram_gb"],
            }
            for k, v in TRIAL_ALLOWED_INSTANCES.items()
        ],
        "os_options": [
            {
                "value": k,
                "label": v["label"],
            }
            for k, v in TRIAL_ALLOWED_OS.items()
        ],
        "storage_gb":  TRIAL_STORAGE_GB,   # Fixed
        "duration_days": TRIAL_DAYS,
        "note": "Storage aur duration fixed hai. Instance type aur OS choose kar sakte ho.",
    }


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

    body          = await request.json()
    instance_type = body.get("instance_type", "t3.micro").strip()
    os_key        = body.get("os", "ubuntu-22.04").strip()
    server_name   = body.get("server_name", "").strip()

    # ── 1. Instance type allowed hai? ──
    if instance_type not in TRIAL_ALLOWED_INSTANCES:
        allowed = ", ".join(TRIAL_ALLOWED_INSTANCES.keys())
        raise HTTPException(400, f"Invalid instance_type. Trial mein allowed: {allowed}")

    # ── 2. OS allowed hai? ──
    if os_key not in TRIAL_ALLOWED_OS:
        allowed = ", ".join(TRIAL_ALLOWED_OS.keys())
        raise HTTPException(400, f"Invalid OS. Trial mein allowed: {allowed}")

    # ── 3. Server name ──
    if not server_name:
        server_name = f"Trial-{user_id}"
    elif len(server_name) > 50:
        raise HTTPException(400, "Server name too long (max 50 characters)")

    # ── 4. User fetch + suspend check ──
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    if user.is_suspended:
        reason = user.suspend_reason or "No reason provided"
        raise HTTPException(403, f"Account suspended: {reason}")

    # ── 5. User already trial le chuka hai? ──
    existing_trial = db.query(Trial).filter(Trial.user_id == user_id).first()
    if existing_trial:
        raise HTTPException(409, "You have already used your free trial")

    # ── 6. Is IP se pehle koi trial hua hai? ──
    ip_trial = db.query(Trial).filter(Trial.ip_address == ip).first()
    if ip_trial:
        raise HTTPException(409, "A trial has already been used from this IP address")

    # ── 7. Trial AWS account dhundo ──
    aws_account = db.query(AWSAccount).filter(
        AWSAccount.type      == AWSAccountType.trial,
        AWSAccount.is_active == True,
    ).order_by(AWSAccount.used_credits).first()

    if not aws_account:
        raise HTTPException(503, "Trial is not available at the moment. Please try again later")

    if aws_account.remaining_credits <= 0:
        raise HTTPException(503, "Trial credits exhausted. Please contact support")

    # ── 8. OS se AMI resolve karo ──
    os_config   = TRIAL_ALLOWED_OS[os_key]
    ami_id      = os_config["ami_id"]
    os_label    = os_config["label"]
    inst_config = TRIAL_ALLOWED_INSTANCES[instance_type]
    expires_at  = datetime.utcnow() + timedelta(days=TRIAL_DAYS)

    # ── 9. VPS record banao (pending) ──
    vps = VPSOrder(
        user_id        = user_id,
        aws_account_id = aws_account.id,
        instance_type  = instance_type,
        ami_id         = ami_id,
        os             = os_label,
        region         = TRIAL_REGION,
        storage_gb     = TRIAL_STORAGE_GB,
        server_name    = server_name,
        vcpu           = inst_config["vcpu"],
        ram_gb         = inst_config["ram_gb"],
        status         = VPSStatus.pending,
        expires_at     = expires_at,
    )
    db.add(vps)
    db.commit()
    db.refresh(vps)

    # ── 10. Trial record banao ──
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

    # ── 11. Celery se background launch ──
    launch_vps_task.delay(
        vps_id         = vps.id,
        user_id        = user_id,
        aws_account_id = aws_account.id,
        config         = {
            "instance_type": instance_type,
            "ami_id":        ami_id,
            "os":            os_label,
            "storage_gb":    TRIAL_STORAGE_GB,
            "server_name":   server_name,
            "region":        TRIAL_REGION,
        },
    )

    return {
        "message":      "Trial started! Your VPS is being set up.",
        "vps_id":       vps.id,
        "status":       "pending",
        "instance_type": instance_type,
        "os":           os_label,
        "storage_gb":   TRIAL_STORAGE_GB,
        "expires_at":   expires_at,
        "info":         f"VPS ready hone mein ~2-3 minutes lagte hain. Track karo: /api/vps/{vps.id}/status",
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
    
