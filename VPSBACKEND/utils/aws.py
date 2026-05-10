import boto3
import os

REGION = os.getenv("AWS_REGION", "ap-south-1")


# ─────────────────────────────────────────
# Per-Account EC2 Client                    ← FIX: har account ke apne keys
# tasks.py aur endpoints isse use karein
# ─────────────────────────────────────────

def get_ec2_for_account(access_key: str, secret_key: str, region: str = None):
    """
    DB se decrypted access_key + secret_key pass karo.
    Har AWS account ke liye alag client banta hai.
    """
    return boto3.client(
        "ec2",
        region_name           = region or REGION,
        aws_access_key_id     = access_key,
        aws_secret_access_key = secret_key,
    )


def get_cloudwatch_for_account(access_key: str, secret_key: str, region: str = None):
    return boto3.client(
        "cloudwatch",
        region_name           = region or REGION,
        aws_access_key_id     = access_key,
        aws_secret_access_key = secret_key,
    )


def get_cost_explorer_for_account(access_key: str, secret_key: str):
    """Cost Explorer sirf us-east-1 mein kaam karta hai."""
    return boto3.client(
        "ce",
        region_name           = "us-east-1",
        aws_access_key_id     = access_key,
        aws_secret_access_key = secret_key,
    )


# ─────────────────────────────────────────
# Helper: DB se AWS account load karke client do
# ─────────────────────────────────────────

def get_ec2_from_db_account(aws_account) -> boto3.client:
    """
    AWSAccount model object pass karo.
    Automatically decrypt karke client return karega.
    """
    from VPSBACKEND.utils.encryption import decrypt
    access_key = decrypt(aws_account.access_key)
    secret_key = decrypt(aws_account.secret_key)
    return get_ec2_for_account(access_key, secret_key, aws_account.region)


def get_cloudwatch_from_db_account(aws_account) -> boto3.client:
    from VPSBACKEND.utils.encryption import decrypt
    access_key = decrypt(aws_account.access_key)
    secret_key = decrypt(aws_account.secret_key)
    return get_cloudwatch_for_account(access_key, secret_key, aws_account.region)


# ─────────────────────────────────────────
# Legacy (ENV-based) — Sirf Plans endpoints ke liye
# Plans AWS se live data fetch karte hain,
# unhe kisi specific account ki zaroorat nahi
# ─────────────────────────────────────────

def get_ec2():
    """Sirf Plans/stock endpoints use karein."""
    return boto3.client(
        "ec2",
        region_name           = REGION,
        aws_access_key_id     = os.getenv("AWS_ACCESS_KEY"),
        aws_secret_access_key = os.getenv("AWS_SECRET_KEY"),
    )
    
