import boto3
import json
import os
from fastapi import APIRouter, HTTPException, Request, Depends
from VPSBACKEND.Login.Coockis import get_current_user

router = APIRouter(prefix="/api/plans", tags=["Plans"])

REGION = os.getenv("AWS_REGION", "ap-south-1")

# AWS region name to pricing location name mapping
REGION_TO_LOCATION = {
    "ap-south-1":     "Asia Pacific (Mumbai)",
    "us-east-1":      "US East (N. Virginia)",
    "us-west-2":      "US West (Oregon)",
    "eu-west-1":      "Europe (Ireland)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "sa-east-1":      "South America (Sao Paulo)",
}


def _get_live_instance_types() -> list[str]:
    """Fetch all available instance types in the region from AWS."""
    ec2   = boto3.client("ec2", region_name=REGION)
    types = []

    paginator = ec2.get_paginator("describe_instance_type_offerings")
    pages     = paginator.paginate(
        LocationType = "region",
        Filters      = [{"Name": "location", "Values": [REGION]}],
    )
    for page in pages:
        for offering in page["InstanceTypeOfferings"]:
            types.append(offering["InstanceType"])

    return types


@router.get("/pricing")
async def get_pricing(
    request:      Request,
    current_user: dict = Depends(get_current_user),
):
    try:
        location = REGION_TO_LOCATION.get(REGION)
        if not location:
            raise HTTPException(400, f"Pricing location not mapped for region: {REGION}")

        # ── Step 1: Get live instance types from AWS ──
        instance_types = _get_live_instance_types()
        if not instance_types:
            raise HTTPException(500, "No instance types found for this region")

        # ── Step 2: Fetch pricing for each ──
        # Pricing API is only in us-east-1
        pricing = boto3.client("pricing", region_name="us-east-1")
        result  = {}

        for instance_type in instance_types:
            try:
                response = pricing.get_products(
                    ServiceCode   = "AmazonEC2",
                    FormatVersion = "aws_bulk_pricing_format",
                    Filters       = [
                        {"Type": "TERM_MATCH", "Field": "instanceType",    "Value": instance_type},
                        {"Type": "TERM_MATCH", "Field": "location",        "Value": location},
                        {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                        {"Type": "TERM_MATCH", "Field": "tenancy",         "Value": "Shared"},
                        {"Type": "TERM_MATCH", "Field": "capacitystatus",  "Value": "Used"},
                        {"Type": "TERM_MATCH", "Field": "preInstalledSw",  "Value": "NA"},
                    ],
                    MaxResults = 1,
                )

                if response["PriceList"]:
                    price_data = json.loads(response["PriceList"][0])
                    terms      = price_data["terms"]["OnDemand"]
                    term       = next(iter(terms.values()))
                    price_dim  = next(iter(term["priceDimensions"].values()))
                    usd_per_hr = float(price_dim["pricePerUnit"]["USD"])

                    result[instance_type] = {
                        "usd_per_hour":  round(usd_per_hr, 6),
                        "usd_per_day":   round(usd_per_hr * 24, 4),
                        "usd_per_month": round(usd_per_hr * 24 * 30, 4),
                    }
                else:
                    result[instance_type] = {
                        "usd_per_hour":  None,
                        "usd_per_day":   None,
                        "usd_per_month": None,
                        "note":          "Pricing not available",
                    }

            except Exception:
                result[instance_type] = {
                    "usd_per_hour":  None,
                    "usd_per_day":   None,
                    "usd_per_month": None,
                    "note":          "Pricing not available",
                }

        return {
            "region":   REGION,
            "location": location,
            "pricing":  result,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch pricing: {str(e)}")
