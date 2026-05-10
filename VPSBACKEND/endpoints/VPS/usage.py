from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import VPSOrder, VPSStatus
from VPSBACKEND.Login.Coockis import get_current_user
from VPSBACKEND.utils.aws import get_cloudwatch
from VPSBACKEND.__main__ import limiter

router = APIRouter(prefix="/api/vps", tags=["VPS"])


@router.get("/{vps_id}/usage")
@limiter.limit("20/minute")
async def get_vps_usage(
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

    if vps.status != VPSStatus.active:
        raise HTTPException(400, "VPS must be running to fetch usage")

    try:
        cw     = get_cloudwatch()
        end    = datetime.utcnow()
        start  = end - timedelta(hours=1)

        def _get_metric(metric_name: str, stat: str = "Average") -> float | None:
            response = cw.get_metric_statistics(
                Namespace  = "AWS/EC2",
                MetricName = metric_name,
                Dimensions = [{"Name": "InstanceId", "Value": vps.instance_id}],
                StartTime  = start,
                EndTime    = end,
                Period     = 3600,
                Statistics = [stat],
            )
            points = response.get("Datapoints", [])
            if points:
                return round(points[-1][stat], 2)
            return None

        return {
            "vps_id":              vps_id,
            "instance_id":         vps.instance_id,
            "cpu_utilization_pct": _get_metric("CPUUtilization"),
            "network_in_bytes":    _get_metric("NetworkIn", "Sum"),
            "network_out_bytes":   _get_metric("NetworkOut", "Sum"),
            "disk_read_bytes":     _get_metric("DiskReadBytes", "Sum"),
            "disk_write_bytes":    _get_metric("DiskWriteBytes", "Sum"),
            "period":              "Last 1 hour",
        }

    except Exception as e:
        raise HTTPException(500, f"Failed to fetch usage: {str(e)}")
