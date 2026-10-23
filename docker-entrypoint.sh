#!/bin/sh
set -e

# The pgvector extension must exist before SQLAlchemy creates tables that
# use Vector columns. Ensure it (and the search index) are present, then run
# the passed command (uvicorn for the API, the consumer for the worker).
python - <<'PY'
import os
from sqlalchemy import create_engine, text

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise SystemExit("DATABASE_URL is required")

engine = create_engine(database_url)
with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
        ON document_chunks USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """))
    conn.commit()
PY

exec "$@"
