import logging
from datetime import datetime, timedelta
from VPSBACKEND.utils.celery_app import celery_app

logger = logging.getLogger("VPSBACKEND")


# ─────────────────────────────────────────
# Launch VPS Task
# ─────────────────────────────────────────

@celery_app.task(bind=True, max_retries=3, name="tasks.launch_vps")
def launch_vps_task(self, vps_id: int, user_id: int, aws_account_id: int, config: dict):
    """
    Background task — EC2 launch + full setup
    config = { instance_type, ami_id, region, storage_gb, server_name, os }
    """
    from VPSBACKEND.database import SessionLocal
    from VPSBACKEND.Database.models import VPSOrder, VPSStatus, AWSAccount
    from VPSBACKEND.utils.aws import get_ec2_from_db_account   # ← FIX: per-account
    from VPSBACKEND.utils.encryption import encrypt

    db = SessionLocal()

    try:
        vps = db.query(VPSOrder).filter(VPSOrder.id == vps_id).first()
        if not vps:
            logger.error(f"VPS {vps_id} not found")
            return

        # ── Load AWS Account ──────────────────
        aws_account = db.query(AWSAccount).filter(AWSAccount.id == aws_account_id).first()
        if not aws_account:
            logger.error(f"AWS account {aws_account_id} not found")
            return

        ec2 = get_ec2_from_db_account(aws_account)              # ← FIX: account ke keys use karo

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
        sg_name = f"vps-sg-{vps_id}-{user_id}"
        sg      = ec2.create_security_group(
            GroupName   = sg_name,
            Description = f"Security group for VPS {vps_id}",
        )
        sg_id = sg["GroupId"]

        ec2.authorize_security_group_ingress(
            GroupId       = sg_id,
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
                        {"Key": "Name",    "Value": config.get("server_name", f"VPS-{vps_id}")},
                        {"Key": "vps_id",  "Value": str(vps_id)},
                        {"Key": "user_id", "Value": str(user_id)},
                    ],
                }
            ],
        )

        instance_id     = instance["Instances"][0]["InstanceId"]
        vps.instance_id = instance_id
        db.commit()

        # ── Step 4: Wait for instance running ──
        logger.info(f"[VPS {vps_id}] Waiting for instance to start...")
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(
            InstanceIds  = [instance_id],
            WaiterConfig = {"Delay": 10, "MaxAttempts": 30},
        )

        # ── Step 5: Elastic IP ──
        logger.info(f"[VPS {vps_id}] Allocating Elastic IP...")
        eip        = ec2.allocate_address(Domain="vpc")
        alloc_id   = eip["AllocationId"]
        elastic_ip = eip["PublicIp"]

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

        # ── Step 6: Email notification (sync)  ← FIX: asyncio.run nahi
        _send_vps_created_email_sync(
            to_email      = vps.user.email,
            server_name   = config.get("server_name", f"VPS-{vps_id}"),
            ip            = elastic_ip,
            instance_type = config["instance_type"],
            os_name       = config.get("os", "Linux"),
            expires_at    = vps.expires_at.strftime("%d %B %Y"),
        )

    except Exception as e:
        logger.error(f"[VPS {vps_id}] Launch failed: {e}")
        try:
            vps        = db.query(VPSOrder).filter(VPSOrder.id == vps_id).first()
            if vps:
                vps.status = VPSStatus.suspended
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=e, countdown=30)

    finally:
        db.close()


# ─────────────────────────────────────────
# Sync Email Helper (Celery ke liye)        ← FIX: asyncio.run nahi
# ─────────────────────────────────────────

def _send_vps_created_email_sync(
    to_email: str,
    server_name: str,
    ip: str,
    instance_type: str,
    os_name: str,
    expires_at: str,
):
    """
    Celery task sync context mein chalta hai.
    Isliye direct smtplib use karo — asyncio.run nahi.
    """
    try:
        from VPSBACKEND.Notification import send_vps_created_email_sync
        send_vps_created_email_sync(
            to_email      = to_email,
            server_name   = server_name,
            ip            = ip,
            instance_type = instance_type,
            os_name       = os_name,
            expires_at    = expires_at,
        )
    except Exception as e:
        logger.error(f"Email send failed: {e}")


# ─────────────────────────────────────────
# Scheduled Tasks
# ─────────────────────────────────────────

@celery_app.task(name="tasks.stop_expired_vps")
def stop_expired_vps():
    """Har ghante chalega — expired VPS stop karo."""
    from VPSBACKEND.database import SessionLocal
    from VPSBACKEND.Database.models import VPSOrder, VPSStatus
    from VPSBACKEND.utils.aws import get_ec2_from_db_account

    db  = SessionLocal()
    now = datetime.utcnow()

    try:
        expired_list = db.query(VPSOrder).filter(
            VPSOrder.status     == VPSStatus.active,
            VPSOrder.expires_at <= now,
        ).all()

        for vps in expired_list:
            try:
                ec2 = get_ec2_from_db_account(vps.aws_account)
                ec2.stop_instances(InstanceIds=[vps.instance_id])
                vps.status = VPSStatus.expired
                db.commit()
                logger.info(f"[Cron] VPS {vps.id} expired and stopped.")

                # ── Trial VPS hai? → User ko expiry email bhejo ──
                from VPSBACKEND.Database.models import Trial
                is_trial = db.query(Trial).filter(
                    Trial.user_id        == vps.user_id,
                    Trial.aws_account_id == vps.aws_account_id,
                ).first()

                if is_trial:
                    try:
                        from VPSBACKEND.Notification import send_trial_expiry_email
                        expired_str = now.strftime("%d %B %Y, %I:%M %p UTC")
                        send_trial_expiry_email(
                            to_email    = vps.user.email,
                            server_name = vps.server_name or f"VPS-{vps.id}",
                            expired_at  = expired_str,
                        )
                        logger.info(f"[Cron] Trial expiry email sent → {vps.user.email}")
                    except Exception as mail_err:
                        logger.error(f"[Cron] Trial expiry email failed: {mail_err}")

            except Exception as e:
                logger.error(f"[Cron] Failed to stop VPS {vps.id}: {e}")

    finally:
        db.close()


@celery_app.task(name="tasks.sync_aws_credits")
def sync_aws_credits():
    """Daily — AWS Cost Explorer se credits sync karo."""
    from VPSBACKEND.database import SessionLocal
    from VPSBACKEND.Database.models import AWSAccount
    from VPSBACKEND.utils.aws import get_cost_explorer_for_account
    from VPSBACKEND.utils.encryption import decrypt
    from datetime import date

    db = SessionLocal()

    try:
        accounts = db.query(AWSAccount).filter(AWSAccount.is_active == True).all()

        for account in accounts:
            try:
                access_key = decrypt(account.access_key)
                secret_key = decrypt(account.secret_key)
                ce         = get_cost_explorer_for_account(access_key, secret_key)

                today      = date.today()
                start      = today.replace(day=1).isoformat()
                end        = today.isoformat()

                result     = ce.get_cost_and_usage(
                    TimePeriod  = {"Start": start, "End": end},
                    Granularity = "MONTHLY",
                    Metrics     = ["UnblendedCost"],
                )

                amount = float(
                    result["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"]
                )

                account.used_credits   = round(amount, 4)
                account.last_synced_at = datetime.utcnow()
                db.commit()

                logger.info(f"[CreditSync] Account {account.id}: used ${amount}")

                # 20% credits bache → admin alert
                if account.remaining_credits < (account.total_credits * 0.20):
                    logger.warning(
                        f"[CreditSync] ⚠️ Account {account.id} ({account.account_alias}) "
                        f"credits low: ${account.remaining_credits:.2f} remaining"
                    )

            except Exception as e:
                logger.error(f"[CreditSync] Account {account.id} failed: {e}")

    finally:
        db.close()

