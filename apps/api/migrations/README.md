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
The Python API automatically creates/updates tables on startup via `Base.metadata.create_all()`. 
However, the SQL migration script is recommended to ensure proper indexing and extension setup.

## Migration Notes

- **001_add_semantic_search.sql**: Adds pgvector support and chunks table
  - Enables `pgvector` extension (1536-dim embeddings for OpenAI)
  - Adds `is_indexed` and `indexed_at` tracking to documents
  - Creates `chunks` table with IVFFlat index for fast similarity search
  - Backward compatible: uses `IF NOT EXISTS` clauses
