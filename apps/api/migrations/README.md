# Database Migrations

This directory contains SQL migration scripts for the AtlasOps database schema.

## Running Migrations

### Option 1: Manual (One-time)
```bash
psql $DATABASE_URL < migrations/001_add_semantic_search.sql
```

### Option 2: With Docker Compose
```bash
# Start PostgreSQL container
docker compose up postgres -d

# Wait for container to be ready, then run migration
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -f /dev/stdin < migrations/001_add_semantic_search.sql
```

### Option 3: Automatic (via SQLAlchemy)
The Python API calls SQLAlchemy's `Base.metadata.create_all()` on startup. This
creates missing tables, but does not add columns to existing tables; apply the
migration when upgrading an existing database.

## Migration Notes

- **001_add_semantic_search.sql**: Adds pgvector support and the `document_chunks` table
  - Enables the `vector` extension for 384-dimensional `all-MiniLM-L6-v2` embeddings
  - Adds `is_indexed` and `indexed_at` tracking to documents
  - Creates `document_chunks` with a `content` column and IVFFlat index for cosine similarity search
  - Backward compatible: uses `IF NOT EXISTS` clauses
