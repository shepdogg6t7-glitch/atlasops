# ADR-001: Use pgvector for Semantic Search

## Status
Accepted

## Context
AtlasOps needs semantic search over document chunks. Options considered:
- Dedicated vector database (Pinecone, Milvus, Qdrant) — adds operational complexity and cost
- PostgreSQL + pgvector extension — keeps all data in one store, leverages existing Postgres dependency

## Decision
Use PostgreSQL 16 with pgvector for vector storage and cosine-similarity search via IVFFlat indexing.

## Consequences
- Positive: Single database to operate, ACID transactions, no extra infrastructure cost
- Negative: Vector search performance tied to Postgres sizing; pgvector extension must be available on the DB host

## Related
docs/architecture/system-architecture.md
