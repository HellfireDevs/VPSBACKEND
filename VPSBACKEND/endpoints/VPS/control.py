from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import VPSOrder, VPSStatus
from VPSBACKEND.Login.Coockis import get_current_user
from VPSBACKEND.utils.aws import get_ec2_from_db_account    # ← FIX: per-account
from VPSBACKEND.utils.limiter import limiter                # ← FIX: limiter.py se

router = APIRouter(prefix="/api/vps", tags=["VPS"])


def _get_vps(vps_id: int, user_id: int, db: Session) -> VPSOrder:
    vps = db.query(VPSOrder).filter(
        VPSOrder.id      == vps_id,
        VPSOrder.user_id == user_id,
    ).first()
    if not vps:
        raise HTTPException(404, "VPS not found")
    if vps.status in [VPSStatus.deleted, VPSStatus.suspended]:
        raise HTTPException(400, f"VPS is {vps.status.value}")
    return vps


@router.post("/{vps_id}/start")
@limiter.limit("20/minute")
async def start_vps(
    vps_id:       int,
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    vps = _get_vps(vps_id, current_user["user_id"], db)

    if vps.status == VPSStatus.active:
        raise HTTPException(400, "VPS is already running")

    try:
        ec2 = get_ec2_from_db_account(vps.aws_account)     # ← FIX
        ec2.start_instances(InstanceIds=[vps.instance_id])
        vps.status = VPSStatus.active
        db.commit()
        return {"message": "VPS started successfully", "vps_id": vps_id}
    except Exception as e:
        raise HTTPException(500, f"Failed to start VPS: {str(e)}")


@router.post("/{vps_id}/stop")
@limiter.limit("20/minute")
async def stop_vps(
    vps_id:       int,
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    vps = _get_vps(vps_id, current_user["user_id"], db)

    if vps.status != VPSStatus.active:
        raise HTTPException(400, "VPS is not running")

    try:
        ec2 = get_ec2_from_db_account(vps.aws_account)     # ← FIX
        ec2.stop_instances(InstanceIds=[vps.instance_id])
        vps.status = VPSStatus.stopped
        db.commit()
        return {"message": "VPS stopped successfully", "vps_id": vps_id}
    except Exception as e:
        raise HTTPException(500, f"Failed to stop VPS: {str(e)}")


@router.post("/{vps_id}/restart")
@limiter.limit("20/minute")
async def restart_vps(
    vps_id:       int,
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    vps = _get_vps(vps_id, current_user["user_id"], db)

    if vps.status != VPSStatus.active:
        raise HTTPException(400, "VPS must be running to restart")

    try:
        ec2 = get_ec2_from_db_account(vps.aws_account)     # ← FIX
        ec2.reboot_instances(InstanceIds=[vps.instance_id])
        return {"message": "VPS restarted successfully", "vps_id": vps_id}
    except Exception as e:
        raise HTTPException(500, f"Failed to restart VPS: {str(e)}")
        
