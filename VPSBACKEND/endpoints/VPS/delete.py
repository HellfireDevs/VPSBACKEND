from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import VPSOrder, VPSStatus
from VPSBACKEND.Login.Coockis import get_current_user
from VPSBACKEND.utils.aws import get_ec2
from VPSBACKEND.__main__ import limiter

router = APIRouter(prefix="/api/vps", tags=["VPS"])


@router.delete("/{vps_id}")
@limiter.limit("10/hour")
async def delete_vps(
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

    if vps.status == VPSStatus.deleted:
        raise HTTPException(400, "VPS is already deleted")

    ec2    = get_ec2()
    errors = []

    # ── Step 1: Disassociate + Release Elastic IP ──
    if vps.elastic_ip_alloc_id:
        try:
            ec2.disassociate_address(
                PublicIp=vps.elastic_ip
            )
            ec2.release_address(
                AllocationId=vps.elastic_ip_alloc_id
            )
        except Exception as e:
            errors.append(f"Elastic IP release failed: {str(e)}")

    # ── Step 2: Terminate EC2 Instance ──
    if vps.instance_id:
        try:
            ec2.terminate_instances(InstanceIds=[vps.instance_id])
        except Exception as e:
            errors.append(f"Instance termination failed: {str(e)}")

    # ── Step 3: Delete Security Group ──
    # Wait a bit for instance to terminate first
    if vps.security_group_id:
        try:
            import time
            time.sleep(5)
            ec2.delete_security_group(GroupId=vps.security_group_id)
        except Exception as e:
            errors.append(f"Security group deletion failed: {str(e)}")

    # ── Step 4: Delete Key Pair ──
    if vps.key_pair_name:
        try:
            ec2.delete_key_pair(KeyName=vps.key_pair_name)
        except Exception as e:
            errors.append(f"Key pair deletion failed: {str(e)}")

    # ── Step 5: Update DB ──
    vps.status = VPSStatus.deleted
    db.commit()

    return {
        "message": "VPS deleted successfully",
        "vps_id":  vps_id,
        "errors":  errors if errors else None,
    }
