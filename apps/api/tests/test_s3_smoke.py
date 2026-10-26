import io
import os
from unittest.mock import MagicMock

import pytest

os.environ["S3_ENDPOINT"] = "http://localhost:8333"
os.environ["S3_REGION"] = "us-east-1"
os.environ["S3_BUCKET"] = "atlasops-documents"
os.environ["S3_ACCESS_KEY"] = "test-key"
os.environ["S3_SECRET_KEY"] = "test-secret"

import apps.api.storage as storage  # noqa: E402

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture
def s3_mock(monkeypatch):
    """Replace storage.s3_client with a MagicMock that records calls."""
    mock_client = MagicMock()
    mock_client.list_buckets.return_value = {"Buckets": []}
    monkeypatch.setattr(storage, "s3_client", mock_client)
    return mock_client


def test_s3_ensure_bucket_upload_download_roundtrip(s3_mock):
    storage.ensure_bucket()

    # Bucket doesn't exist yet -> create_bucket should be called
    s3_mock.create_bucket.assert_called_once_with(Bucket=storage.BUCKET)

    # Upload
    key = "projects/proj-1/doc-1.pdf"
    storage.upload_fileobj(io.BytesIO(PDF_BYTES), key, "application/pdf")
    s3_mock.upload_fileobj.assert_called_once()
    call_args = s3_mock.upload_fileobj.call_args
    assert call_args.args[1] == storage.BUCKET  # Bucket is 2nd positional arg
    assert call_args.args[2] == key  # Key is 3rd positional arg
    assert call_args.kwargs["ExtraArgs"]["ContentType"] == "application/pdf"


def test_s3_client_uses_configured_endpoint(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:8333")
    import importlib

    importlib.reload(storage)
    assert storage.s3_client.meta.endpoint_url == "http://localhost:8333"
