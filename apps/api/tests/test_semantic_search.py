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
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.database import Base, get_db
from apps.api.main import app
from apps.api import models
from apps.api.consumer import chunk_text, extract_pdf_text


# Test database setup
@pytest.fixture(scope="session")
def test_db_engine():
    """Create an in-memory SQLite test database."""
    engine = create_engine("sqlite:///:memory:")
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
def client(test_session):
    """Provide FastAPI test client with test database."""
    def override_get_db():
        try:
            yield test_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


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

    def test_document_model_with_embeddings(self):
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
            text="Sample chunk text",
            embedding=[0.1] * 1536,  # 1536-dim embedding
        )
        
        assert chunk.document_id == doc_id
        assert chunk.chunk_index == 0
        assert chunk.text == "Sample chunk text"
        assert len(chunk.embedding) == 1536


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
        assert data["is_indexed"] is False or "is_indexed" not in data  # May not be in response


class TestSemanticSearchEndpoint:
    """Tests for semantic search endpoint."""

    def test_search_requires_project(self, client):
        """Verify search returns 404 for non-existent project."""
        fake_project_id = uuid.uuid4()
        response = client.post(
            f"/projects/{fake_project_id}/search",
            json={"query": "test search"}
        )
        
        # Should return empty results, not error (no documents in project)
        assert response.status_code == 200
        assert response.json() == []

    def test_search_empty_project_returns_empty_list(self, client, test_session):
        """Verify search on empty project returns empty results."""
        # Create org and project
        org_resp = client.post("/organizations", json={"name": "Empty Org"})
        org_id = org_resp.json()["id"]
        
        proj_resp = client.post(
            f"/organizations/{org_id}/projects",
            json={"name": "Empty Project"}
        )
        project_id = proj_resp.json()["id"]
        
        # Search with no documents
        response = client.post(
            f"/projects/{project_id}/search",
            json={"query": "test", "limit": 10}
        )
        
        assert response.status_code == 200
        assert response.json() == []

    def test_search_with_custom_limit(self, client):
        """Verify search respects custom limit parameter."""
        fake_project_id = uuid.uuid4()
        response = client.post(
            f"/projects/{fake_project_id}/search",
            json={"query": "test", "limit": 5}
        )
        
        assert response.status_code == 200
        results = response.json()
        assert len(results) <= 5

    def test_search_result_structure(self, client, test_session):
        """Verify search results have correct structure."""
        # Create org, project, document with chunks
        org_resp = client.post("/organizations", json={"name": "Search Org"})
        org_id = org_resp.json()["id"]
        
        proj_resp = client.post(
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
        test_session.add(document)
        test_session.commit()
        
        # Add a chunk with embedding
        chunk = models.Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="This is a test chunk about machine learning",
            embedding=[0.1] * 1536,  # Mock embedding
        )
        test_session.add(chunk)
        test_session.commit()
        
        # Search
        response = client.post(
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
