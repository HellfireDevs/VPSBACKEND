import boto3
import os

REGION = os.getenv("AWS_REGION", "ap-south-1")


def get_ec2():
    return boto3.client(
        "ec2",
        region_name          = REGION,
        aws_access_key_id    = os.getenv("AWS_ACCESS_KEY"),
        aws_secret_access_key= os.getenv("AWS_SECRET_KEY"),
    )


def get_cloudwatch():
    return boto3.client(
        "cloudwatch",
        region_name          = REGION,
        aws_access_key_id    = os.getenv("AWS_ACCESS_KEY"),
        aws_secret_access_key= os.getenv("AWS_SECRET_KEY"),
    )
