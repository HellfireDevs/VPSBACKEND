import boto3
import os
from fastapi import APIRouter, HTTPException, Request, Depends
from VPSBACKEND.Login.Coockis import get_current_user

router = APIRouter(prefix="/api/plans", tags=["Plans"])

REGION = os.getenv("AWS_REGION", "ap-south-1")

# AWS SSM paths — AWS khud inhe update karta rehta hai
# No hardcoding — always latest AMI
SSM_PATHS = {
    "Ubuntu 22.04 LTS": {
        "path": "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id",
        "type": "linux",
    },
    "Ubuntu 20.04 LTS": {
        "path": "/aws/service/canonical/ubuntu/server/20.04/stable/current/amd64/hvm/ebs-gp2/ami-id",
        "type": "linux",
    },
    "Debian 12": {
        "path": "/aws/service/debian/release/12/latest/amd64/hvm/ebs/ami-id",
        "type": "linux",
    },
    "Windows Server 2022": {
        "path": "/aws/service/ami-windows-latest/Windows_Server-2022-English-Full-Base",
        "type": "windows",
    },
    "Windows Server 2019": {
        "path": "/aws/service/ami-windows-latest/Windows_Server-2019-English-Full-Base",
        "type": "windows",
    },
}


@router.get("/ami")
async def get_ami_list(
    request:      Request,
    current_user: dict = Depends(get_current_user),
):
    try:
        ssm = boto3.client("ssm", region_name=REGION)
        ec2 = boto3.client("ec2", region_name=REGION)

        ami_ids   = {}
        ami_list  = []
        errors    = []

        # ── Step 1: SSM se latest AMI IDs fetch karo ──
        for os_label, info in SSM_PATHS.items():
            try:
                response = ssm.get_parameter(Name=info["path"])
                ami_id   = response["Parameter"]["Value"]
                ami_ids[ami_id] = {
                    "os":   os_label,
                    "type": info["type"],
                }
            except Exception as e:
                errors.append({"os": os_label, "error": str(e)})

        if not ami_ids:
            raise HTTPException(500, "Could not fetch any AMI IDs from AWS SSM")

        # ── Step 2: EC2 se AMI details fetch karo ──
        details = ec2.describe_images(
            ImageIds=list(ami_ids.keys()),
            Filters=[{"Name": "state", "Values": ["available"]}],
        )

        for img in details["Images"]:
            ami_id = img["ImageId"]
            meta   = ami_ids.get(ami_id, {})

            ami_list.append({
                "ami_id":       ami_id,
                "os":           meta.get("os", "Unknown"),
                "type":         meta.get("type", "linux"),
                "description":  img.get("Description", ""),
                "architecture": img.get("Architecture", "x86_64"),
                "created_at":   img.get("CreationDate", ""),
            })

        # Sort: linux first, then windows
        ami_list.sort(key=lambda x: (x["type"] == "windows", x["os"]))

        return {
            "ami_list": ami_list,
            "errors":   errors if errors else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch AMI list: {str(e)}")
