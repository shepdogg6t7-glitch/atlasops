import os
import uuid
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import engine, get_db, Base
import models
from storage import ensure_bucket, upload_fileobj

Base.metadata.create_all(bind=engine)
ensure_bucket()

app = FastAPI(title="AtlasOps API")

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
def upload_document(project_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db)):
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
