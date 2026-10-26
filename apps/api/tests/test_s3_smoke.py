import io
import os

import boto3
import pytest
from moto import mock_aws

from apps.api.storage import BUCKET, ensure_bucket, s3_client, upload_fileobj

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture
def s3_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:8333")
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.setenv("S3_BUCKET", "atlasops-documents")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")


@mock_aws
def test_s3_ensure_bucket_upload_download_roundtrip(s3_env):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="atlasops-documents")

    ensure_bucket()

    existing = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
    assert "atlasops-documents" in existing

    key = "projects/proj-1/doc-1.pdf"
    upload_fileobj(io.BytesIO(PDF_BYTES), key, "application/pdf")

    obj = client.get_object(Bucket="atlasops-documents", Key=key)
    downloaded = obj["Body"].read()
    assert downloaded == PDF_BYTES


@mock_aws
def test_s3_client_uses_configured_endpoint(s3_env, monkeypatch):
    from apps.api import storage

    monkeypatch.setattr(storage, "s3_client", s3_client)

    assert s3_client.meta.endpoint_url == "http://localhost:8333"
