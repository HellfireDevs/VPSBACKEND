from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import VPSOrder, VPSStatus
from VPSBACKEND.Login.Coockis import get_current_user
from VPSBACKEND.utils.aws import get_ec2
from VPSBACKEND.__main__ import limiter

router = APIRouter(prefix="/api/vps", tags=["VPS"])


@router.get("/")
async def list_vps(
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    vps_list = db.query(VPSOrder).filter(
        VPSOrder.user_id == current_user["user_id"],
        VPSOrder.status  != VPSStatus.deleted,
    ).all()

    return {
        "vps_list": [
            {
                "id":            v.id,
                "server_name":   v.server_name,
                "instance_type": v.instance_type,
                "os":            v.os,
                "status":        v.status,
                "elastic_ip":    v.elastic_ip,
                "region":        v.region,
                "storage_gb":    v.storage_gb,
                "expires_at":    v.expires_at,
                "created_at":    v.created_at,
            }
            for v in vps_list
        ]
    }


@router.get("/{vps_id}/status")
@limiter.limit("30/minute")
async def get_vps_status(
    vps_id:       int,
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    vps = db.query(VPSOrder).filter(
        VPSOrder.id      == vps_id,
        VPSOrder.user_id == current_user["user_id"],
    ).first()

    if not vps:
        raise HTTPException(404, "VPS not found")

    aws_status = None

    # If instance exists, get live status from AWS
    if vps.instance_id and vps.status not in [VPSStatus.deleted, VPSStatus.pending]:
        try:
            ec2      = get_ec2()
            response = ec2.describe_instance_status(
                InstanceIds          = [vps.instance_id],
                IncludeAllInstances  = True,
            )
            if response["InstanceStatuses"]:
                inst       = response["InstanceStatuses"][0]
                aws_status = {
                    "state":          inst["InstanceState"]["Name"],
                    "system_check":   inst["SystemStatus"]["Status"],
                    "instance_check": inst["InstanceStatus"]["Status"],
                }
        except Exception:
            pass

    return {
        "id":            vps.id,
        "server_name":   vps.server_name,
        "instance_type": vps.instance_type,
        "os":            vps.os,
        "status":        vps.status,
        "elastic_ip":    vps.elastic_ip,
        "region":        vps.region,
        "storage_gb":    vps.storage_gb,
        "expires_at":    vps.expires_at,
        "created_at":    vps.created_at,
        "aws_status":    aws_status,
    }
