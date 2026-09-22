-- Migration: Add semantic search infrastructure
-- Enables pgvector extension and creates chunks table

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add indexing metadata to documents table
ALTER TABLE documents
ADD COLUMN IF NOT EXISTS is_indexed BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMP;

-- Create chunks table for storing text chunks with embeddings
CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, chunk_index)
);

-- Create index on document_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);

-- Create index on embedding for vector similarity search
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
