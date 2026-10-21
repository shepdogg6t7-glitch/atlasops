import os
import uuid
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from limits.errors import StorageError
from pydantic import BaseModel, Field
from redis.exceptions import RedisError
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from aiokafka import AIOKafkaProducer
from slowapi.errors import RateLimitExceeded

from apps.api.database import engine, get_db, Base
from apps.api import models
from apps.api.storage import ensure_bucket, upload_fileobj
from apps.api.auth import (
    create_access_token,
    get_current_user,
    get_signing_secret,
    hash_password,
    normalize_email,
    verify_password,
)
from apps.api.ratelimit import (
    limit_ask,
    limit_login,
    limit_register,
    limit_search,
    limit_upload,
    limiter,
    rate_limit_exceeded_handler,
    rate_limit_storage_error_handler,
)
from apps.api.uploads import reject_oversized_request, sanitize_filename, validate_pdf_upload
from apps.api.llm import LLMService

REDPANDA_BOOTSTRAP = os.getenv("REDPANDA_BOOTSTRAP", "localhost:19092")

producer: AIOKafkaProducer | None = None
embedding_model = None
llm_service: LLMService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global producer, llm_service
    get_signing_secret()
    Base.metadata.create_all(bind=engine)
    ensure_bucket()
    producer = AIOKafkaProducer(bootstrap_servers=REDPANDA_BOOTSTRAP)
    await producer.start()
    llm_service = LLMService()
    try:
        yield
    finally:
        await producer.stop()
        await llm_service.aclose()


app = FastAPI(title="AtlasOps API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_exception_handler(RedisError, rate_limit_storage_error_handler)
app.add_exception_handler(StorageError, rate_limit_storage_error_handler)

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
    name: str = Field(min_length=1, max_length=200)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class SemanticSearchQuery(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=10, ge=1, le=50)


class AskQuery(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=5, ge=1, le=20)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    organization_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


def _organization_response(org: models.Organization):
    return {"id": str(org.id), "name": org.name}


def _require_organization_membership(
    organization_id: uuid.UUID,
    user: models.User,
    db: Session,
) -> models.Organization:
    organization = (
        db.query(models.Organization)
        .join(models.OrganizationMembership)
        .filter(
            models.Organization.id == organization_id,
            models.OrganizationMembership.user_id == user.id,
        )
        .first()
    )
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


def _require_project_membership(
    project_id: uuid.UUID,
    user: models.User,
    db: Session,
) -> models.Project:
    project = (
        db.query(models.Project)
        .join(models.OrganizationMembership, models.Project.organization_id == models.OrganizationMembership.organization_id)
        .filter(
            models.Project.id == project_id,
            models.OrganizationMembership.user_id == user.id,
        )
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _create_user_organization(email: str, password: str, organization_name: str, db: Session):
    user = models.User(email=email, password_hash=hash_password(password))
    organization = models.Organization(name=organization_name)
    db.add_all([user, organization])
    db.flush()
    db.add(models.OrganizationMembership(user_id=user.id, organization_id=organization.id, role="owner"))
    return user, organization


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
@limiter.limit(limit_register)
def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)):
    if os.getenv("ALLOW_REGISTRATION", "false").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise HTTPException(status_code=403, detail="Registration is disabled")
    get_signing_secret()
    email = normalize_email(payload.email)
    organization_name = payload.organization_name.strip()
    if not organization_name:
        raise HTTPException(status_code=422, detail="Organization name is required")
    try:
        user, organization = _create_user_organization(
            email, payload.password, organization_name, db
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.query(models.User).filter(models.User.email == email).first() is not None:
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        raise
    db.refresh(user)
    db.refresh(organization)
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": {"id": str(user.id), "email": user.email},
        "organizations": [_organization_response(organization)],
    }


@app.post("/auth/login")
@limiter.limit(limit_login)
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    get_signing_secret()
    email = normalize_email(payload.email)
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    memberships = (
        db.query(models.Organization)
        .join(models.OrganizationMembership)
        .filter(models.OrganizationMembership.user_id == user.id)
        .all()
    )
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": {"id": str(user.id), "email": user.email},
        "organizations": [_organization_response(org) for org in memberships],
    }


@app.get("/organizations")
def list_organizations(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    organizations = (
        db.query(models.Organization)
        .join(models.OrganizationMembership)
        .filter(models.OrganizationMembership.user_id == user.id)
        .all()
    )
    return [_organization_response(org) for org in organizations]


@app.post("/organizations")
def create_organization(
    payload: OrganizationCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Organization name is required")
    org = models.Organization(name=name)
    db.add(org)
    db.flush()
    db.add(models.OrganizationMembership(user_id=user.id, organization_id=org.id, role="owner"))
    db.commit()
    db.refresh(org)
    return _organization_response(org)


@app.get("/organizations/{org_id}/projects")
def list_projects(
    org_id: uuid.UUID,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_organization_membership(org_id, user, db)
    projects = db.query(models.Project).filter(models.Project.organization_id == org_id).all()
    return [
        {"id": str(project.id), "name": project.name, "organization_id": str(org_id)}
        for project in projects
    ]


@app.post("/organizations/{org_id}/projects")
def create_project(
    org_id: uuid.UUID,
    payload: ProjectCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_organization_membership(org_id, user, db)

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Project name is required")
    project = models.Project(name=name, organization_id=org_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": str(project.id), "name": project.name, "organization_id": str(project.organization_id)}


@app.post("/projects/{project_id}/documents")
@limiter.limit(limit_upload)
async def upload_document(
    request: Request,
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_project_membership(project_id, user, db)
    if producer is None:
        raise HTTPException(status_code=503, detail="Document event service is unavailable")

    reject_oversized_request(request.headers.get("content-length"))
    size_bytes = validate_pdf_upload(file)
    filename = sanitize_filename(file.filename)

    storage_key = f"{project_id}/{uuid.uuid4()}-{filename}"
    upload_fileobj(file.file, storage_key, "application/pdf")

    doc = models.Document(
        filename=filename,
        content_type="application/pdf",
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
def list_documents(
    project_id: uuid.UUID,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_project_membership(project_id, user, db)
    docs = db.query(models.Document).filter(models.Document.project_id == project_id).all()
    return [
        {"id": str(d.id), "filename": d.filename, "size_bytes": d.size_bytes, "status": d.status}
        for d in docs
    ]


@app.post("/projects/{project_id}/search")
@limiter.limit(limit_search)
def semantic_search(
    request: Request,
    project_id: uuid.UUID,
    payload: SemanticSearchQuery,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_project_membership(project_id, user, db)
    global embedding_model
    if embedding_model is None:
        from sentence_transformers import SentenceTransformer
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

    # Generate embedding for query
    query_embedding = embedding_model.encode(payload.query).tolist()

    # Search for similar chunks in this project
    chunks = (
        db.query(
            models.Chunk.id,
            models.Chunk.content,
            models.Chunk.chunk_index,
            models.Document.id.label("document_id"),
            models.Document.filename,
            models.Chunk.embedding.cosine_distance(query_embedding).label("distance")
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
            "text": c.content,
            "similarity_score": 1 - c.distance  # Convert distance to similarity (0-1)
        }
        for c in chunks
    ]


@app.post("/projects/{project_id}/ask")
@limiter.limit(limit_ask)
def ask_question(
    request: Request,
    project_id: uuid.UUID,
    payload: AskQuery,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_project_membership(project_id, user, db)
    global embedding_model
    if llm_service is None:
        raise HTTPException(status_code=503, detail="LLM service is unavailable")
    if embedding_model is None:
        from sentence_transformers import SentenceTransformer
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

    # Retrieve relevant chunks via semantic search
    query_embedding = embedding_model.encode(payload.question).tolist()

    chunks = (
        db.query(
            models.Chunk.id,
            models.Chunk.content,
            models.Chunk.chunk_index,
            models.Document.id.label("document_id"),
            models.Document.filename,
            models.Chunk.embedding.cosine_distance(query_embedding).label("distance")
        )
        .join(models.Document, models.Chunk.document_id == models.Document.id)
        .filter(models.Document.project_id == project_id)
        .filter(models.Chunk.embedding.isnot(None))
        .order_by("distance")
        .limit(payload.limit)
        .all()
    )

    if not chunks:
        return {"answer": "No relevant document content found to answer the question.", "sources": []}

    chunk_list = [
        {
            "chunk_id": str(c.id),
            "document_id": str(c.document_id),
            "filename": c.filename,
            "chunk_index": c.chunk_index,
            "text": c.content,
            "similarity_score": 1 - c.distance,
        }
        for c in chunks
    ]

    import asyncio

    answer = asyncio.run(llm_service.generate_answer(payload.question, chunk_list))

    return {
        "answer": answer,
        "sources": [
            {
                "chunk_id": c["chunk_id"],
                "document_id": c["document_id"],
                "filename": c["filename"],
                "chunk_index": c["chunk_index"],
                "similarity_score": c["similarity_score"],
            }
            for c in chunk_list
        ],
    }
