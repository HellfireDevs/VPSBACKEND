import time
import logging
from datetime import datetime, timedelta
from VPSBACKEND.utils.celery_app import celery_app

logger = logging.getLogger("VPSBACKEND")


@celery_app.task(bind=True, max_retries=3, name="tasks.launch_vps")
def launch_vps_task(self, vps_id: int, user_id: int, aws_account_id: int, config: dict):
    """
    Background task — EC2 launch + full setup
    config = {
        instance_type, ami_id, region,
        storage_gb, server_name
    }
    """
    from VPSBACKEND.database import SessionLocal
    from VPSBACKEND.Database.models import VPSOrder, VPSStatus, AWSAccount
    from VPSBACKEND.utils.aws import get_ec2
    from VPSBACKEND.utils.encryption import encrypt

    db  = SessionLocal()
    ec2 = get_ec2()

    try:
        vps = db.query(VPSOrder).filter(VPSOrder.id == vps_id).first()
        if not vps:
            logger.error(f"VPS {vps_id} not found")
            return

        # ── Step 1: Create Key Pair ──
        logger.info(f"[VPS {vps_id}] Creating key pair...")
        key_name     = f"vps-{vps_id}-{user_id}"
        key_response = ec2.create_key_pair(KeyName=key_name)
        pem_data     = key_response["KeyMaterial"]

        vps.key_pair_name      = key_name
        vps.pem_file_encrypted = encrypt(pem_data)
        db.commit()

        # ── Step 2: Create Security Group ──
        logger.info(f"[VPS {vps_id}] Creating security group...")
        sg_name  = f"vps-sg-{vps_id}-{user_id}"
        sg       = ec2.create_security_group(
            GroupName   = sg_name,
            Description = f"Security group for VPS {vps_id}",
        )
        sg_id = sg["GroupId"]

        # Default rules — SSH + RDP
        ec2.authorize_security_group_ingress(
            GroupId    = sg_id,
            IpPermissions = [
                {
                    "IpProtocol": "tcp",
                    "FromPort":   22,
                    "ToPort":     22,
                    "IpRanges":   [{"CidrIp": "0.0.0.0/0"}],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort":   3389,
                    "ToPort":     3389,
                    "IpRanges":   [{"CidrIp": "0.0.0.0/0"}],
                },
            ],
        )

        vps.security_group_id = sg_id
        db.commit()

        # ── Step 3: Launch EC2 Instance ──
        logger.info(f"[VPS {vps_id}] Launching EC2 instance...")
        instance = ec2.run_instances(
            ImageId          = config["ami_id"],
            InstanceType     = config["instance_type"],
            KeyName          = key_name,
            SecurityGroupIds = [sg_id],
            MinCount         = 1,
            MaxCount         = 1,
            BlockDeviceMappings = [
                {
                    "DeviceName": "/dev/sda1",
                    "Ebs": {
                        "VolumeSize":          config.get("storage_gb", 20),
                        "VolumeType":          "gp3",
                        "DeleteOnTermination": True,
                    },
                }
            ],
            TagSpecifications = [
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name",   "Value": config.get("server_name", f"VPS-{vps_id}")},
                        {"Key": "vps_id", "Value": str(vps_id)},
                        {"Key": "user_id","Value": str(user_id)},
                    ],
                }
            ],
        )

        instance_id = instance["Instances"][0]["InstanceId"]
        vps.instance_id = instance_id
        db.commit()

        # ── Step 4: Wait for instance to be running ──
        logger.info(f"[VPS {vps_id}] Waiting for instance to start...")
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(
            InstanceIds    = [instance_id],
            WaiterConfig   = {"Delay": 10, "MaxAttempts": 30},
        )

        # ── Step 5: Allocate + Associate Elastic IP ──
        logger.info(f"[VPS {vps_id}] Allocating Elastic IP...")
        eip          = ec2.allocate_address(Domain="vpc")
        alloc_id     = eip["AllocationId"]
        elastic_ip   = eip["PublicIp"]

        ec2.associate_address(
            InstanceId   = instance_id,
            AllocationId = alloc_id,
        )

        vps.elastic_ip          = elastic_ip
        vps.elastic_ip_alloc_id = alloc_id
        vps.status              = VPSStatus.active
        vps.expires_at          = datetime.utcnow() + timedelta(days=30)
        db.commit()

        logger.info(f"[VPS {vps_id}] Ready! IP: {elastic_ip}")

        # ── Step 6: Send email notification ──
        import asyncio
        from VPSBACKEND.Notification import send_vps_created_email
        asyncio.run(send_vps_created_email(
            to_email      = vps.user.email,
            server_name   = config.get("server_name", f"VPS-{vps_id}"),
            ip            = elastic_ip,
            instance_type = config["instance_type"],
            os_name       = config.get("os", "Linux"),
            expires_at    = vps.expires_at.strftime("%d %B %Y"),
        ))

    except Exception as e:
        logger.error(f"[VPS {vps_id}] Launch failed: {e}")

        # Mark as failed in DB
        try:
            vps        = db.query(VPSOrder).filter(VPSOrder.id == vps_id).first()
            vps.status = VPSStatus.suspended
            db.commit()
        except Exception:
            pass

        raise self.retry(exc=e, countdown=30)

    finally:
        db.close()
