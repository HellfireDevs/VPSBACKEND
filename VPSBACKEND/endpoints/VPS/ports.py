from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import VPSOrder, VPSStatus, PortRule
from VPSBACKEND.Login.Coockis import get_current_user
from VPSBACKEND.utils.aws import get_ec2
from VPSBACKEND.__main__ import limiter

router = APIRouter(prefix="/api/vps", tags=["VPS"])

BLOCKED_PORTS = [25, 465, 587]  # SMTP — AWS blocks these by default


@router.get("/{vps_id}/ports")
async def list_ports(
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

    ports = db.query(PortRule).filter(PortRule.vps_id == vps_id).all()

    return {
        "ports": [
            {
                "port":       p.port,
                "protocol":   p.protocol,
                "is_open":    p.is_open,
                "created_at": p.created_at,
            }
            for p in ports
        ]
    }


@router.post("/{vps_id}/ports/open")
@limiter.limit("10/minute")
async def open_port(
    vps_id:       int,
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    body     = await request.json()
    port     = body.get("port")
    protocol = body.get("protocol", "tcp").lower()

    if not port:
        raise HTTPException(400, "Port is required")

    if not isinstance(port, int) or port < 1 or port > 65535:
        raise HTTPException(400, "Port must be between 1 and 65535")

    if port in BLOCKED_PORTS:
        raise HTTPException(403, f"Port {port} is blocked by AWS policy")

    if protocol not in ["tcp", "udp"]:
        raise HTTPException(400, "Protocol must be tcp or udp")

    vps = db.query(VPSOrder).filter(
        VPSOrder.id      == vps_id,
        VPSOrder.user_id == current_user["user_id"],
    ).first()
    if not vps:
        raise HTTPException(404, "VPS not found")

    if vps.status == VPSStatus.deleted:
        raise HTTPException(400, "VPS is deleted")

    # Check if already open
    existing = db.query(PortRule).filter(
        PortRule.vps_id   == vps_id,
        PortRule.port     == port,
        PortRule.protocol == protocol,
        PortRule.is_open  == True,
    ).first()
    if existing:
        raise HTTPException(409, f"Port {port}/{protocol} is already open")

    try:
        ec2 = get_ec2()
        ec2.authorize_security_group_ingress(
            GroupId       = vps.security_group_id,
            IpPermissions = [
                {
                    "IpProtocol": protocol,
                    "FromPort":   port,
                    "ToPort":     port,
                    "IpRanges":   [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to open port: {str(e)}")

    rule = PortRule(
        vps_id   = vps_id,
        port     = port,
        protocol = protocol,
        is_open  = True,
    )
    db.add(rule)
    db.commit()

    return {"message": f"Port {port}/{protocol} opened successfully"}


@router.delete("/{vps_id}/ports/close")
@limiter.limit("10/minute")
async def close_port(
    vps_id:       int,
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    body     = await request.json()
    port     = body.get("port")
    protocol = body.get("protocol", "tcp").lower()

    vps = db.query(VPSOrder).filter(
        VPSOrder.id      == vps_id,
        VPSOrder.user_id == current_user["user_id"],
    ).first()
    if not vps:
        raise HTTPException(404, "VPS not found")

    rule = db.query(PortRule).filter(
        PortRule.vps_id   == vps_id,
        PortRule.port     == port,
        PortRule.protocol == protocol,
        PortRule.is_open  == True,
    ).first()
    if not rule:
        raise HTTPException(404, f"Port {port}/{protocol} is not open")

    try:
        ec2 = get_ec2()
        ec2.revoke_security_group_ingress(
            GroupId       = vps.security_group_id,
            IpPermissions = [
                {
                    "IpProtocol": protocol,
                    "FromPort":   port,
                    "ToPort":     port,
                    "IpRanges":   [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to close port: {str(e)}")

    rule.is_open = False
    db.commit()

    return {"message": f"Port {port}/{protocol} closed successfully"}
