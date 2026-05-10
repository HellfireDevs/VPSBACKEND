import boto3
import os
from fastapi import APIRouter, HTTPException, Request, Depends
from VPSBACKEND.Login.Coockis import get_current_user

router = APIRouter(prefix="/api/plans", tags=["Plans"])

REGION = os.getenv("AWS_REGION", "ap-south-1")


@router.get("/instances")
async def get_instances(
    request:      Request,
    current_user: dict = Depends(get_current_user),
):
    try:
        ec2        = boto3.client("ec2", region_name=REGION)
        all_types  = []

        # ── Step 1: Get all available instance types in this region ──
        paginator = ec2.get_paginator("describe_instance_type_offerings")
        pages     = paginator.paginate(
            LocationType = "region",
            Filters      = [
                {"Name": "location", "Values": [REGION]},
            ],
        )
        for page in pages:
            for offering in page["InstanceTypeOfferings"]:
                all_types.append(offering["InstanceType"])

        if not all_types:
            raise HTTPException(500, "No instance types found for this region")

        # ── Step 2: Get full details for all available types ──
        instances = []
        # AWS allows max 100 per request — paginate in chunks
        chunk_size = 100
        for i in range(0, len(all_types), chunk_size):
            chunk    = all_types[i:i + chunk_size]
            response = ec2.describe_instance_types(InstanceTypes=chunk)

            for inst in response["InstanceTypes"]:
                instances.append({
                    "instance_type":  inst["InstanceType"],
                    "vcpu":           inst["VCpuInfo"]["DefaultVCpus"],
                    "ram_gb":         round(inst["MemoryInfo"]["SizeInMiB"] / 1024, 2),
                    "network":        inst.get("NetworkInfo", {}).get("NetworkPerformance", "Unknown"),
                    "arch":           inst.get("ProcessorInfo", {}).get("SupportedArchitectures", []),
                    "storage":        inst.get("InstanceStorageInfo", {}).get("TotalSizeInGB", 0),
                    "ebs_optimized":  inst.get("EbsInfo", {}).get("EbsOptimizedSupport", "unsupported"),
                })

        # Sort by vcpu then ram
        instances.sort(key=lambda x: (x["vcpu"], x["ram_gb"]))

        return {
            "region":    REGION,
            "count":     len(instances),
            "instances": instances,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch instance types: {str(e)}")
