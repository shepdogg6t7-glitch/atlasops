import os
import uuid
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from aiokafka import AIOKafkaProducer
from sentence_transformers import SentenceTransformer

from apps.api.database import engine, get_db, Base
from apps.api import models
from apps.api.llm import (
    LLMConfigurationError,
    LLMProviderError,
    LLMQuotaError,
    generate_answer,
)
from apps.api.storage import ensure_bucket, upload_fileobj

Base.metadata.create_all(bind=engine)
ensure_bucket()

REDPANDA_BOOTSTRAP = os.getenv("REDPANDA_BOOTSTRAP", "localhost:19092")

producer: AIOKafkaProducer | None = None
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global producer
    producer = AIOKafkaProducer(bootstrap_servers=REDPANDA_BOOTSTRAP)
    await producer.start()
    yield
    await producer.stop()


app = FastAPI(title="AtlasOps API", lifespan=lifespan)

cors_origin = os.getenv("CORS_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[cors_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


class OrganizationCreate(BaseModel):
    name: str


class ProjectCreate(BaseModel):
    name: str


class SemanticSearchQuery(BaseModel):
    query: str
    limit: int = 10


class AskQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10)


def _retrieve_chunks(db: Session, project_id: uuid.UUID, query: str, limit: int):
    query_embedding = embedding_model.encode(query).tolist()
    chunks = (
        db.query(
            models.Chunk.id,
            models.Chunk.content,
            models.Chunk.chunk_index,
            models.Document.id.label("document_id"),
            models.Document.filename,
            models.Chunk.embedding.cosine_distance(query_embedding).label("distance"),
        )
        .join(models.Document, models.Chunk.document_id == models.Document.id)
        .filter(models.Document.project_id == project_id)
        .filter(models.Chunk.embedding.isnot(None))
        .order_by("distance")
        .limit(limit)
        .all()
    )
    return [
        {
            "chunk_id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "filename": chunk.filename,
            "chunk_index": chunk.chunk_index,
            "text": chunk.content,
            "similarity_score": 1 - chunk.distance,
        }
        for chunk in chunks
    ]


@app.post("/organizations")
def create_organization(payload: OrganizationCreate, db: Session = Depends(get_db)):
    org = models.Organization(name=payload.name)
    db.add(org)
    db.commit()
    db.refresh(org)
    return {"id": str(org.id), "name": org.name}


@app.post("/organizations/{org_id}/projects")
def create_project(org_id: uuid.UUID, payload: ProjectCreate, db: Session = Depends(get_db)):
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    project = models.Project(name=payload.name, organization_id=org_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": str(project.id), "name": project.name, "organization_id": str(project.organization_id)}


@app.post("/projects/{project_id}/documents")
async def upload_document(project_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    file.file.seek(0, 2)
    size_bytes = file.file.tell()
    file.file.seek(0)

    storage_key = f"{project_id}/{uuid.uuid4()}-{file.filename}"
    upload_fileobj(file.file, storage_key, file.content_type or "application/octet-stream")

    doc = models.Document(
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size_bytes,
        storage_key=storage_key,
        project_id=project_id,
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    event = {"event": "document.uploaded", "document_id": str(doc.id), "project_id": str(project_id)}
    await producer.send_and_wait("document.uploaded", json.dumps(event).encode("utf-8"))

    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "size_bytes": doc.size_bytes,
        "status": doc.status,
    }


@app.get("/projects/{project_id}/documents")
def list_documents(project_id: uuid.UUID, db: Session = Depends(get_db)):
    docs = db.query(models.Document).filter(models.Document.project_id == project_id).all()
    return [
        {"id": str(d.id), "filename": d.filename, "size_bytes": d.size_bytes, "status": d.status}
        for d in docs
    ]


@app.post("/projects/{project_id}/search")
def semantic_search(project_id: uuid.UUID, payload: SemanticSearchQuery, db: Session = Depends(get_db)):
    return _retrieve_chunks(db, project_id, payload.query, payload.limit)


@app.post("/projects/{project_id}/ask")
def ask_project(project_id: uuid.UUID, payload: AskQuestion, db: Session = Depends(get_db)):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be empty.")

    sources = _retrieve_chunks(db, project_id, question, payload.limit)
    if not sources:
        return {
            "answer": "I couldn't find any indexed document passages relevant to your question.",
            "sources": [],
        }

    context = "\n\n".join(
        f"[{source['filename']}, chunk {source['chunk_index'] + 1}]\n{source['text']}"
        for source in sources
    )
    try:
        answer = generate_answer(question, context)
    except LLMQuotaError as exc:
        raise HTTPException(
            status_code=503,
            detail="Gemini free-tier quota is temporarily exhausted. Try again later.",
        ) from exc
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail="Gemini could not complete the request. Try again later.",
        ) from exc

    return {"answer": answer, "sources": sources}
