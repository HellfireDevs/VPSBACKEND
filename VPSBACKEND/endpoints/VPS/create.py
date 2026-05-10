import os
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import VPSOrder, VPSStatus, AWSAccount, AWSAccountType
from VPSBACKEND.Login.Coockis import get_current_user
from VPSBACKEND.utils.limiter import limiter
from VPSBACKEND.utils.tasks import launch_vps_task

router = APIRouter(prefix="/api/vps", tags=["VPS"])


@router.post("/create")
@limiter.limit("5/hour")
async def create_vps(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    body          = await request.json()
    instance_type = body.get("instance_type")
    ami_id        = body.get("ami_id")
    os_name       = body.get("os", "Linux")
    storage_gb    = body.get("storage_gb", 20)
    server_name   = body.get("server_name", "").strip()
    region        = os.getenv("AWS_REGION", "ap-south-1")
    user_id       = current_user["user_id"]

    # ── 1. Validate input ──
    if not instance_type or not ami_id:
        raise HTTPException(400, "instance_type and ami_id are required")

    if not server_name:
        raise HTTPException(400, "server_name is required")

    if storage_gb < 20 or storage_gb > 1000:
        raise HTTPException(400, "storage_gb must be between 20 and 1000")

    # ── 2. Find available paid AWS account ──
    aws_account = db.query(AWSAccount).filter(
        AWSAccount.type      == AWSAccountType.paid,
        AWSAccount.is_active == True,
    ).order_by(AWSAccount.used_credits).first()

    if not aws_account:
        raise HTTPException(503, "No AWS accounts available at the moment")

    # ── 3. Check credits ──
    if aws_account.remaining_credits <= 0:
        raise HTTPException(503, "Insufficient credits on AWS account")

    # ── 4. Create VPS record in DB (pending) ──
    vps = VPSOrder(
        user_id        = user_id,
        aws_account_id = aws_account.id,
        instance_type  = instance_type,
        ami_id         = ami_id,
        os             = os_name,
        region         = region,
        storage_gb     = storage_gb,
        server_name    = server_name,
        status         = VPSStatus.pending,
    )
    db.add(vps)
    db.commit()
    db.refresh(vps)

    # ── 5. Launch in background via Celery ──
    launch_vps_task.delay(
        vps_id         = vps.id,
        user_id        = user_id,
        aws_account_id = aws_account.id,
        config         = {
            "instance_type": instance_type,
            "ami_id":        ami_id,
            "os":            os_name,
            "storage_gb":    storage_gb,
            "server_name":   server_name,
            "region":        region,
        },
    )

    return {
        "message":    "VPS creation started",
        "vps_id":     vps.id,
        "status":     "pending",
        "info":       "Use /api/vps/{id}/status to track progress",
    }
    
