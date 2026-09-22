import os
import uuid
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from aiokafka import AIOKafkaProducer
from sentence_transformers import SentenceTransformer

from apps.api.database import engine, get_db, Base
from apps.api import models
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
    # Generate embedding for query
    query_embedding = embedding_model.encode(payload.query).tolist()

    # Search for similar chunks in this project
    chunks = (
        db.query(
            models.Chunk.id,
            models.Chunk.text,
            models.Chunk.chunk_index,
            models.Document.id.label("document_id"),
            models.Document.filename,
            func.cosine_distance(models.Chunk.embedding, query_embedding).label("distance")
        )
        .join(models.Document, models.Chunk.document_id == models.Document.id)
        .filter(models.Document.project_id == project_id)
        .filter(models.Chunk.embedding.isnot(None))
        .order_by("distance")
        .limit(payload.limit)
        .all()
    )

    return [
        {
            "chunk_id": str(c.id),
            "document_id": str(c.document_id),
            "filename": c.filename,
            "chunk_index": c.chunk_index,
            "text": c.text,
            "similarity_score": 1 - c.distance  # Convert distance to similarity (0-1)
        }
        for c in chunks
    ]
