from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import VPSOrder, VPSStatus
from VPSBACKEND.Login.Coockis import get_current_user
from VPSBACKEND.utils.encryption import decrypt
from VPSBACKEND.__main__ import limiter

router = APIRouter(prefix="/api/vps", tags=["VPS"])


@router.get("/{vps_id}/pem")
@limiter.limit("5/hour")
async def download_pem(
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
        raise HTTPException(400, "VPS is deleted")

    if not vps.pem_file_encrypted:
        raise HTTPException(404, "PEM file not found for this VPS")

    try:
        pem_data = decrypt(vps.pem_file_encrypted)
    except Exception:
        raise HTTPException(500, "Failed to decrypt PEM file")

    filename = f"{vps.server_name or f'vps-{vps_id}'}.pem"

    return Response(
        content     = pem_data,
        media_type  = "application/x-pem-file",
        headers     = {
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )
