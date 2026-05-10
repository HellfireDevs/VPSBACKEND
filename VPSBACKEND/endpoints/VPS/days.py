from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import VPSOrder, VPSStatus, AWSAccount
from VPSBACKEND.Login.Coockis import get_current_user

router = APIRouter(prefix="/api/vps", tags=["VPS"])


@router.get("/{vps_id}/days-remaining")
async def days_remaining(
    vps_id:       int,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    vps = db.query(VPSOrder).filter(
        VPSOrder.id      == vps_id,
        VPSOrder.user_id == current_user["user_id"],
    ).first()

    if not vps:
        raise HTTPException(404, "VPS not found")

    if vps.status == VPSStatus.deleted:
        raise HTTPException(400, "VPS is deleted")

    if not vps.expires_at:
        return {"days_remaining": None, "message": "No expiry set"}

    now            = datetime.utcnow()
    remaining      = vps.expires_at - now
    days_left      = max(remaining.days, 0)
    hours_left     = max(int(remaining.total_seconds() // 3600), 0)

    # Credits info from AWS account
    aws            = db.query(AWSAccount).filter(
        AWSAccount.id == vps.aws_account_id
    ).first()

    return {
        "vps_id":            vps_id,
        "expires_at":        vps.expires_at,
        "days_remaining":    days_left,
        "hours_remaining":   hours_left,
        "is_expired":        days_left == 0,
        "credits_remaining": aws.remaining_credits if aws else None,
    }
