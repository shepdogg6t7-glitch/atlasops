import io

import pytest

from apps.api.storage import storage_client, S3_BUCKET


def test_s3_upload_download_roundtrip():
    """Verify S3-compatible storage (SeaweedFS) accept/store/retrieve."""
    content = b"seaweedfs smoke test data"
    key = "smoke-test/sample.txt"

    # Upload
    storage_client.put_object(Bucket=S3_BUCKET, Key=key, Body=io.BytesIO(content))

    # Download
    resp = storage_client.get_object(Bucket=S3_BUCKET, Key=key)
    assert resp["Body"].read() == content

    # Cleanup
    storage_client.delete_object(Bucket=S3_BUCKET, Key=key)
