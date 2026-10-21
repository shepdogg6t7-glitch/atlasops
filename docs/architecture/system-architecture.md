# AtlasOps System Architecture

## Overview

Mermaid diagrams for the AtlasOps system architecture, data flows, and deployment topology.

```mermaid
graph TB
    subgraph Client["Client / Browser"]
        UI[Next.js Web UI]
    end

    subgraph API["API Layer (FastAPI)"]
        Auth[Authentication / JWT]
        Org[Organization & Project Mgmt]
        Upload[Document Upload]
        Search[Semantic Search]
        Health[Health Check]
    end

    subgraph Services["Backing Services (Docker Compose)"]
        DB[(PostgreSQL 16 + pgvector)]
        MinIO[(MinIO / S3-compatible)]
        Redpanda[(Redpanda / Kafka)]
        Redis[(Redis 7)]
    end

    subgraph Worker["Ingestion Worker"]
        Consumer[Kafka Consumer]
        Extract[PDF Extract / Chunk]
        Embed[SentenceTransformer Embeddings]
    end

    UI -->|HTTPS/HTTP| API
    Auth --> DB
    Org --> DB
    Upload --> MinIO
    Upload --> DB
    Upload -->|emit document.uploaded| Redpanda
    Search --> DB
    Health --> DB

    Redpanda --> Consumer
    Consumer -->|download| MinIO
    Consumer --> Extract
    Extract --> Embed
    Embed -->|store chunks + vectors| DB

    style Client fill:#e1f5fe,stroke:#01579b
    style API fill:#f3e5f5,stroke:#4a148c
    style Services fill:#fff3e0,stroke:#e65100
    style Worker fill:#e8f5e9,stroke:#1b5e20
```

## Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| Next.js Web UI | Client interface for auth, project/docs management, search |
| FastAPI API | Auth, org/project CRUD, document upload, semantic search, health |
| PostgreSQL + pgvector | Organizations, projects, documents, chunks, embeddings, vector search |
| MinIO | PDF object storage (S3-compatible) |
| Redpanda | Event streaming for document.uploaded (decouples upload from indexing) |
| Redis | Rate-limit storage (optional; memory:// default) |
| Ingestion Worker | Consumes upload events, extracts/chunks/embeds PDFs, writes to DB |
