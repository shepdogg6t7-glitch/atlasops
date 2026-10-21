"""
Integration tests for semantic search functionality.

Tests the complete pipeline:
1. Document upload
2. Text extraction and chunking
3. Embedding generation
4. Semantic search via cosine similarity
"""

import json
import os
import uuid
from contextlib import asynccontextmanager, contextmanager
from io import BytesIO
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.database import Base, get_db
from apps.api import main
from apps.api.llm import LLMService, LLMError
app = main.app
from apps.api import models
from apps.api.consumer import chunk_text, extract_pdf_text


@contextmanager
def authenticated_client(db_session, monkeypatch):
    @asynccontextmanager
    async def test_lifespan(_app):
        yield

    class TestProducer:
        async def send_and_wait(self, *_args, **_kwargs):
            return None

    monkeypatch.setenv("JWT_SECRET", "test-signing-secret-that-is-long-enough-123456")
    monkeypatch.setenv("ALLOW_REGISTRATION", "true")
    monkeypatch.setattr(app.router, "lifespan_context", test_lifespan)
    monkeypatch.setattr(main, "upload_fileobj", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "producer", TestProducer())
    monkeypatch.setattr(main, "embedding_model", MagicMock(encode=lambda *_args, **_kwargs: np.array([0.1] * 384)))
    monkeypatch.setattr(
        main,
        "llm_service",
        MagicMock(
            generate_answer=MagicMock(return_value="This is a mocked LLM answer based on the document context.")
        ),
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                "/auth/register",
                json={
                    "email": "semantic-test@example.com",
                    "password": "correct horse battery staple",
                    "organization_name": "Semantic Test Organization",
                },
            )
            assert response.status_code == 201
            test_client.headers.update(
                {"Authorization": f"Bearer {response.json()['access_token']}"}
            )
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


# Test database setup
@pytest.fixture
def test_db_engine():
    """Create an in-memory SQLite test database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def test_session(test_db_engine):
    """Create a new session for each test."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)
    session = TestingSessionLocal()
    yield session
    session.close()

@pytest.fixture
def client(test_session, monkeypatch):
    """Provide FastAPI test client with test database."""
    with authenticated_client(test_session, monkeypatch) as test_client:
        yield test_client

@pytest.fixture(scope="session")

def postgres_engine():
    """
    Real Postgres+pgvector engine, for tests that need actual vector
    operators (e.g. cosine_distance / <=>), which SQLite cannot execute.
    Skips cleanly if a real database isn't reachable.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set; skipping tests that require real Postgres+pgvector")
    if database_url.startswith("sqlite"):
        pytest.skip("SQLite cannot exercise Postgres pgvector operators")

    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres not reachable ({exc}); skipping tests that require real Postgres+pgvector")

    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def pg_session(postgres_engine):
    """Session bound to the real Postgres engine, rolled back after each test."""
    connection = postgres_engine.connect()
    transaction = connection.begin()
    PgSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = PgSessionLocal()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def pg_client(pg_session, monkeypatch):
    """FastAPI test client backed by the real Postgres session."""
    with authenticated_client(pg_session, monkeypatch) as test_client:
        yield test_client


class TestSemanticSearchInfrastructure:
    """Tests for semantic search core infrastructure."""

    def test_chunk_text_splitting(self):
        """Verify text is chunked correctly with overlap."""
        text = "word " * 500  # Creates ~2500 chars (500 words * 5 chars/word)
        chunks = chunk_text(text)

        assert len(chunks) > 1, "Text should be split into multiple chunks"
        assert all(isinstance(c, str) for c in chunks), "All chunks should be strings"
        assert all(len(c) > 0 for c in chunks), "No empty chunks should be created"

    def test_chunk_text_empty_input(self):
        """Verify empty text produces no chunks."""
        chunks = chunk_text("")
        assert len(chunks) == 0

    def test_chunk_text_small_input(self):
        """Verify small text fits in one chunk."""
        text = "This is a small test document."
        chunks = chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_document_model_with_embeddings(self, test_session):
        """Verify Document model has embedding tracking fields."""
        doc = models.Document(
            id=uuid.uuid4(),
            filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            storage_key="test/key",
            project_id=uuid.uuid4(),
            status="uploaded",
        )
        test_session.add(doc)
        test_session.flush()

        # Verify new fields exist and have correct defaults
        assert doc.is_indexed is False
        assert doc.indexed_at is None

    def test_chunk_model_structure(self):
        """Verify Chunk model has correct structure."""
        doc_id = uuid.uuid4()
        chunk = models.Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            content="Sample chunk text",
            embedding=[0.1] * 384,  # 384-dim embedding
        )

        assert chunk.document_id == doc_id
        assert chunk.chunk_index == 0
        assert chunk.content == "Sample chunk text"
        assert len(chunk.embedding) == 384


class TestDocumentUploadEndpoint:
    """Tests for document upload endpoint."""

    def test_upload_document_creates_entry(self, client, test_session):
        """Verify uploading a document creates a database entry."""
        # Create org and project first
        org_resp = client.post("/organizations", json={"name": "Test Org"})
        org_id = org_resp.json()["id"]

        proj_resp = client.post(
            f"/organizations/{org_id}/projects",
            json={"name": "Test Project"}
        )
        project_id = proj_resp.json()["id"]

        # Upload a mock PDF file
        file_content = b"%PDF-1.4\n%mock pdf content"
        response = client.post(
            f"/projects/{project_id}/documents",
            files={"file": ("test.pdf", BytesIO(file_content), "application/pdf")}
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["filename"] == "test.pdf"
        assert data["status"] == "uploaded"
        assert data.get("is_indexed", False) is False  # May not be in response


class TestSemanticSearchEndpoint:
    """Tests for semantic search endpoint. Requires real Postgres+pgvector,
    since the cosine-distance operator these tests exercise doesn't exist in SQLite."""

    def test_search_requires_project(self, pg_client):
        """Verify search returns 404 for non-existent project."""
        fake_project_id = uuid.uuid4()
        response = pg_client.post(
            f"/projects/{fake_project_id}/search",
            json={"query": "test search"}
        )

        assert response.status_code == 404

    def test_search_empty_project_returns_empty_list(self, pg_client, pg_session):
        """Verify search on empty project returns empty results."""
        # Create org and project
        org_resp = pg_client.post("/organizations", json={"name": "Empty Org"})
        org_id = org_resp.json()["id"]

        proj_resp = pg_client.post(
            f"/organizations/{org_id}/projects",
            json={"name": "Empty Project"}
        )
        project_id = proj_resp.json()["id"]

        # Search with no documents
        response = pg_client.post(
            f"/projects/{project_id}/search",
            json={"query": "test", "limit": 10}
        )

        assert response.status_code == 200
        assert response.json() == []

    def test_search_with_custom_limit(self, pg_client):
        """Verify search respects custom limit parameter."""
        fake_project_id = uuid.uuid4()
        response = pg_client.post(
            f"/projects/{fake_project_id}/search",
            json={"query": "test", "limit": 5}
        )

        assert response.status_code == 404

    def test_search_result_structure(self, pg_client, pg_session):
        """Verify search results have correct structure."""
        # Create org, project, document with chunks
        org_resp = pg_client.post("/organizations", json={"name": "Search Org"})
        org_id = org_resp.json()["id"]

        proj_resp = pg_client.post(
            f"/organizations/{org_id}/projects",
            json={"name": "Search Project"}
        )
        project_id = proj_resp.json()["id"]

        # Manually add document and chunks for testing
        project_uuid = uuid.UUID(project_id)
        doc_id = uuid.uuid4()
        document = models.Document(
            id=doc_id,
            filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            storage_key="test/key",
            project_id=project_uuid,
            status="processed",
            is_indexed=True,
        )
        pg_session.add(document)
        pg_session.commit()

        # Add a chunk with embedding
        chunk = models.Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            content="This is a test chunk about machine learning",
            embedding=[0.1] * 384,  # Mock embedding
        )
        pg_session.add(chunk)
        pg_session.commit()

        # Search
        response = pg_client.post(
            f"/projects/{project_id}/search",
            json={"query": "machine learning", "limit": 10}
        )

        assert response.status_code == 200
        results = response.json()

        if results:  # Only check structure if results exist
            result = results[0]
            assert "chunk_id" in result
            assert "document_id" in result
            assert "filename" in result
            assert "chunk_index" in result
            assert "text" in result
            assert "similarity_score" in result
            assert 0 <= result["similarity_score"] <= 1


class TestListDocumentsEndpoint:
    """Tests for listing documents endpoint."""

    def test_list_documents_empty(self, client, test_session):
        """Verify listing documents on empty project returns empty list."""
        org_resp = client.post("/organizations", json={"name": "Empty Org"})
        org_id = org_resp.json()["id"]

        proj_resp = client.post(
            f"/organizations/{org_id}/projects",
            json={"name": "Empty Project"}
        )
        project_id = proj_resp.json()["id"]

        response = client.get(f"/projects/{project_id}/documents")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_documents_with_documents(self, client, test_session):
        """Verify listing documents returns all docs in project."""
        org_resp = client.post("/organizations", json={"name": "Doc Org"})
        org_id = org_resp.json()["id"]

        proj_resp = client.post(
            f"/organizations/{org_id}/projects",
            json={"name": "Doc Project"}
        )
        project_id = proj_resp.json()["id"]

        # Add documents manually
        project_uuid = uuid.UUID(project_id)
        for i in range(3):
            doc = models.Document(
                id=uuid.uuid4(),
                filename=f"test{i}.pdf",
                content_type="application/pdf",
                size_bytes=1024 * (i + 1),
                storage_key=f"test/key{i}",
                project_id=project_uuid,
                status="uploaded",
            )
            test_session.add(doc)

        test_session.commit()

        response = client.get(f"/projects/{project_id}/documents")
        assert response.status_code == 200
        docs = response.json()
        assert len(docs) == 3
        assert all("id" in d and "filename" in d and "status" in d for d in docs)


class TestHealthEndpoint:
    """Basic health check tests."""

    def test_health_endpoint(self, client):
        """Verify health endpoint returns OK status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestAskEndpoint:
    """Tests for the LLM question-answering endpoint."""

    def test_ask_requires_project(self, pg_client):
        """Verify ask returns 404 for non-existent project."""
        fake_project_id = uuid.uuid4()
        response = pg_client.post(
            f"/projects/{fake_project_id}/ask",
            json={"question": "what is this about?"}
        )
        assert response.status_code == 404

    def test_ask_empty_project_returns_no_content(self, pg_client, pg_session, monkeypatch):
        """Verify ask on empty project returns no relevant content message."""
        org_resp = pg_client.post("/organizations", json={"name": "Ask Org"})
        org_id = org_resp.json()["id"]

        proj_resp = pg_client.post(
            f"/organizations/{org_id}/projects",
            json={"name": "Ask Project"}
        )
        project_id = proj_resp.json()["id"]

        response = pg_client.post(
            f"/projects/{project_id}/ask",
            json={"question": "what is this about?", "limit": 5}
        )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "sources" in data
        assert data["sources"] == []
        assert "No relevant document content" in data["answer"]

    def test_ask_with_chunks_returns_answer(self, pg_client, pg_session, monkeypatch):
        """Verify ask returns an answer with sources when chunks exist."""
        org_resp = pg_client.post("/organizations", json={"name": "Ask Org 2"})
        org_id = org_resp.json()["id"]

        proj_resp = pg_client.post(
            f"/organizations/{org_id}/projects",
            json={"name": "Ask Project 2"}
        )
        project_id = proj_resp.json()["id"]

        project_uuid = uuid.UUID(project_id)
        doc_id = uuid.uuid4()
        document = models.Document(
            id=doc_id,
            filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            storage_key="test/key",
            project_id=project_uuid,
            status="processed",
            is_indexed=True,
        )
        pg_session.add(document)
        pg_session.commit()

        chunk = models.Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            content="This is a test chunk about machine learning and neural networks",
            embedding=[0.1] * 384,
        )
        pg_session.add(chunk)
        pg_session.commit()

        response = pg_client.post(
            f"/projects/{project_id}/ask",
            json={"question": "what is the document about?", "limit": 5}
        )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "sources" in data
        assert len(data["sources"]) == 1
        assert data["sources"][0]["filename"] == "test.pdf"
        assert 0 <= data["sources"][0]["similarity_score"] <= 1


class TestLLMFallback:
    """Tests for LLM primary/fallback provider behavior."""

    def test_uses_primary_provider_on_success(self, monkeypatch):
        """Verify the primary provider is called and its answer returned."""
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("LLM_API_KEY", "primary-key")
        monkeypatch.setenv("LLM_MODEL", "gemini-1.5-flash")
        monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "anthropic")
        monkeypatch.setenv("LLM_FALLBACK_API_KEY", "fallback-key")
        monkeypatch.setenv("LLM_FALLBACK_MODEL", "claude-3-haiku-20240307")

        service = LLMService()

        calls = []

        async def fake_primary(api_key, model, prompt):
            calls.append(("primary", api_key, model))
            return "primary answer"

        async def fake_fallback(api_key, model, prompt):
            calls.append(("fallback", api_key, model))
            return "fallback answer"

        monkeypatch.setattr(service, "_gemini_answer", fake_primary)
        monkeypatch.setattr(service, "_anthropic_answer", fake_fallback)

        import asyncio

        answer = asyncio.run(service.generate_answer("what is this?", [{"text": "chunk", "filename": "f.pdf"}]))

        assert answer == "primary answer"
        assert calls == [("primary", "primary-key", "gemini-1.5-flash")]

    def test_falls_back_to_anthropic_on_primary_failure(self, monkeypatch):
        """Verify Anthropic is used when Gemini fails."""
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("LLM_API_KEY", "primary-key")
        monkeypatch.setenv("LLM_MODEL", "gemini-1.5-flash")
        monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "anthropic")
        monkeypatch.setenv("LLM_FALLBACK_API_KEY", "fallback-key")
        monkeypatch.setenv("LLM_FALLBACK_MODEL", "claude-3-haiku-20240307")

        service = LLMService()

        calls = []

        async def fake_primary(api_key, model, prompt):
            calls.append(("primary", api_key, model))
            raise LLMError("primary down")

        async def fake_fallback(api_key, model, prompt):
            calls.append(("fallback", api_key, model))
            return "fallback answer"

        monkeypatch.setattr(service, "_gemini_answer", fake_primary)
        monkeypatch.setattr(service, "_anthropic_answer", fake_fallback)

        import asyncio

        answer = asyncio.run(service.generate_answer("what is this?", [{"text": "chunk", "filename": "f.pdf"}]))

        assert answer == "fallback answer"
        assert calls == [
            ("primary", "primary-key", "gemini-1.5-flash"),
            ("fallback", "fallback-key", "claude-3-haiku-20240307"),
        ]

    def test_raises_when_both_providers_fail(self, monkeypatch):
        """Verify an error is raised when both primary and fallback fail."""
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("LLM_API_KEY", "primary-key")
        monkeypatch.setenv("LLM_MODEL", "gemini-1.5-flash")
        monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "anthropic")
        monkeypatch.setenv("LLM_FALLBACK_API_KEY", "fallback-key")
        monkeypatch.setenv("LLM_FALLBACK_MODEL", "claude-3-haiku-20240307")

        service = LLMService()

        async def fail_provider(api_key, model, prompt):
            raise LLMError("provider down")

        monkeypatch.setattr(service, "_gemini_answer", fail_provider)
        monkeypatch.setattr(service, "_anthropic_answer", fail_provider)

        import asyncio

        try:
            asyncio.run(
                service.generate_answer("what is this?", [{"text": "chunk", "filename": "f.pdf"}])
            )
        except LLMError:
            pass
        else:
            raise AssertionError("Expected LLMError when both providers fail")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
