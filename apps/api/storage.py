import os
import boto3
from dotenv import load_dotenv

load_dotenv()

s3_client = boto3.client(
    "s3",
    endpoint_url=os.getenv("S3_ENDPOINT"),
    aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
    region_name="us-east-1",
)

BUCKET = os.getenv("S3_BUCKET")


def ensure_bucket():
    existing = [b["Name"] for b in s3_client.list_buckets().get("Buckets", [])]
    if BUCKET not in existing:
        s3_client.create_bucket(Bucket=BUCKET)


def upload_fileobj(fileobj, key, content_type):
    s3_client.upload_fileobj(fileobj, BUCKET, key, ExtraArgs={"ContentType": content_type})
