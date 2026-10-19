import io

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from apps.api import main
from apps.api.tests.test_auth import bearer, client, register  # noqa: F401
from apps.api.ratelimit import limiter
from apps.api.uploads import sanitize_filename

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


class FakeProducer:
    def __init__(self):
        self.sent = []

    async def send_and_wait(self, topic, value):
        self.sent.append((topic, value))


@pytest.fixture
def upload_env(client, monkeypatch):  # noqa: F811
    stored = []
    producer = FakeProducer()
    monkeypatch.setattr(main, "producer", producer)
    monkeypatch.setattr(
        main, "upload_fileobj", lambda fileobj, key, content_type: stored.append((key, content_type))
    )
    account = register(client, "uploader@example.com")
    headers = bearer(account["access_token"])
    org_id = account["organizations"][0]["id"]
    project = client.post(f"/organizations/{org_id}/projects", json={"name": "P"}, headers=headers)
    assert project.status_code == 200
    return client, headers, project.json()["id"], stored, producer


def upload(client, headers, project_id, name, content, content_type="application/pdf"):
    return client.post(
        f"/projects/{project_id}/documents",
        headers=headers,
        files={"file": (name, io.BytesIO(content), content_type)},
    )


def test_valid_pdf_is_accepted_and_normalized(upload_env):
    client, headers, project_id, stored, producer = upload_env
    response = upload(client, headers, project_id, "../../etc/Report Q3.pdf", PDF_BYTES, "text/plain")
    assert response.status_code == 200
    assert response.json()["filename"] == "Report Q3.pdf"
    key, content_type = stored[0]
    assert key.startswith(f"{project_id}/") and key.endswith("-Report Q3.pdf")
    assert ".." not in key
    assert content_type == "application/pdf"
    assert len(producer.sent) == 1


def test_non_pdf_is_rejected_even_with_pdf_name_and_type(upload_env):
    client, headers, project_id, stored, producer = upload_env
    response = upload(client, headers, project_id, "evil.pdf", b"MZ\x90\x00not a pdf")
    assert response.status_code == 415
    assert stored == [] and producer.sent == []


def test_empty_file_is_rejected(upload_env):
    client, headers, project_id, stored, _ = upload_env
    response = upload(client, headers, project_id, "empty.pdf", b"")
    assert response.status_code == 400
    assert stored == []


def test_oversized_file_is_rejected(upload_env, monkeypatch):
    client, headers, project_id, stored, producer = upload_env
    monkeypatch.setenv("MAX_UPLOAD_MB", "0.001")
    response = upload(client, headers, project_id, "big.pdf", PDF_BYTES + b"0" * 5000)
    assert response.status_code == 413
    assert stored == [] and producer.sent == []


def test_upload_is_rate_limited_per_user(upload_env, monkeypatch):
    client, headers, project_id, stored, producer = upload_env
    monkeypatch.setenv("RATE_LIMIT_UPLOAD", "1/minute")
    first = upload(client, headers, project_id, "first.pdf", PDF_BYTES)
    second = upload(client, headers, project_id, "second.pdf", PDF_BYTES)
    assert first.status_code == 200
    assert second.status_code == 429
    assert len(stored) == 1 and len(producer.sent) == 1


def test_upload_requires_membership_before_validation(client, upload_env):
    _, _, project_id, stored, _ = upload_env
    other = register(client, "other@example.com")
    response = upload(client, bearer(other["access_token"]), project_id, "a.pdf", PDF_BYTES)
    assert response.status_code == 404
    assert stored == []


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("../../secret.pdf", "secret.pdf"),
        ("C:\\Users\\me\\doc.pdf", "doc.pdf"),
        ("name\x00with\x1fcontrol.pdf", "namewithcontrol.pdf"),
        ("", "document.pdf"),
        (None, "document.pdf"),
        ("...", "document.pdf"),
        ("a" * 400 + ".pdf", "a" * 196 + ".pdf"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_login_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_LOGIN", "3/minute")
    body = {"email": "nobody@example.com", "password": "wrong password here"}
    statuses = [client.post("/auth/login", json=body).status_code for _ in range(5)]
    assert statuses[:3] == [401, 401, 401]
    assert statuses[3:] == [429, 429]
    blocked = client.post("/auth/login", json=body)
    assert blocked.headers["Retry-After"].isdigit()
    assert "detail" in blocked.json()


def test_rate_limit_storage_failure_fails_closed_with_503(client, monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise RedisConnectionError("Redis is unavailable")

    monkeypatch.setattr(limiter._storage, "incr", unavailable)
    response = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "wrong password here"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Rate-limit storage is unavailable."


def test_register_is_rate_limited(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REGISTER", "2/hour")
    codes = []
    for i in range(3):
        response = client.post(
            "/auth/register",
            json={
                "email": f"user{i}@example.com",
                "password": "correct horse battery staple",
                "organization_name": "Org",
            },
        )
        codes.append(response.status_code)
    assert codes == [201, 201, 429]


def test_search_limit_is_per_user_not_shared(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_SEARCH", "2/minute")
    first = register(client, "a@example.com")
    second = register(client, "b@example.com")
    fake_project = "00000000-0000-0000-0000-000000000000"

    def search(token):
        return client.post(
            f"/projects/{fake_project}/search", json={"query": "x"}, headers=bearer(token)
        ).status_code

    assert [search(first["access_token"]) for _ in range(3)] == [404, 404, 429]
    assert search(second["access_token"]) == 404
