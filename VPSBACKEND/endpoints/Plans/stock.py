from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
import boto3
import os

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import PlanStock
from VPSBACKEND.Login.Coockis import get_current_user, require_admin

router = APIRouter(prefix="/api/plans", tags=["Plans"])

REGION = os.getenv("AWS_REGION", "ap-south-1")


def _get_live_instance_types() -> list[str]:
    """
    Fetch available instance types live from AWS.
    No hardcoding — whatever AWS returns for this region.
    """
    ec2   = boto3.client("ec2", region_name=REGION)
    types = []

    paginator = ec2.get_paginator("describe_instance_type_offerings")
    pages     = paginator.paginate(
        LocationType = "region",
        Filters      = [
            {"Name": "location", "Values": [REGION]},
        ],
    )

    for page in pages:
        for offering in page["InstanceTypeOfferings"]:
            types.append(offering["InstanceType"])

    return sorted(types)


def _sync_stock_with_aws(db: Session):
    """
    Sync DB stock table with live AWS instance types.
    - New types from AWS → add to DB as available
    - Types no longer on AWS → mark unavailable in DB
    """
    live_types = set(_get_live_instance_types())
    db_entries = {s.instance_type: s for s in db.query(PlanStock).all()}

    # Add new ones from AWS
    for instance_type in live_types:
        if instance_type not in db_entries:
            db.add(PlanStock(
                instance_type = instance_type,
                is_available  = True,
            ))

    # Mark removed ones as unavailable
    for instance_type, stock in db_entries.items():
        if instance_type not in live_types:
            stock.is_available = False

    db.commit()


@router.get("/stock")
async def get_stock(
    request: Request,
    db:      Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        _sync_stock_with_aws(db)
    except Exception as e:
        # If AWS call fails, still return DB data
        pass

    stock = db.query(PlanStock).order_by(PlanStock.instance_type).all()

    return {
        "stock": [
            {
                "instance_type": s.instance_type,
                "available":     s.is_available,
                "updated_at":    s.updated_at,
            }
            for s in stock
        ]
    }


@router.put("/stock/{instance_type}/toggle")
async def toggle_stock(
    instance_type: str,
    request:       Request,
    db:            Session = Depends(get_db),
    admin:         dict    = Depends(require_admin),
):
    stock = db.query(PlanStock).filter(
        PlanStock.instance_type == instance_type
    ).first()

    if not stock:
        raise HTTPException(404, f"Instance type '{instance_type}' not found in database")

    stock.is_available = not stock.is_available
    stock.updated_by   = admin["user_id"]
    db.commit()

    status = "available" if stock.is_available else "out of stock"
    return {
        "instance_type": instance_type,
        "available":     stock.is_available,
        "message":       f"{instance_type} is now {status}",
    }
