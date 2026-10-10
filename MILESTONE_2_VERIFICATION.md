# Milestone 2 implementation reference

This document summarizes implementation details visible in the current source.
It is not a test report, compatibility guarantee, or deployment sign-off.
Current test status is documented in [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md).

## Database and processing

- The migration creates `document_chunks` with a `content` column and
  `vector(384)` embedding column.
- The embedding model is `all-MiniLM-L6-v2`.
- The consumer extracts PDF text, creates 1,000-character chunks with
  200-character overlap, stores embeddings, and sets the document's
  `is_indexed` and `indexed_at` fields on successful processing.

## API routes

- `GET /health`
- `POST /organizations`
- `POST /organizations/{org_id}/projects`
- `POST /projects/{project_id}/documents`
- `GET /projects/{project_id}/documents`
- `POST /projects/{project_id}/search`

The search request contains `query` and optional `limit` (default `10`). Each
result includes `chunk_id`, `document_id`, `filename`, `chunk_index`, `text`,
and `similarity_score`; `text` maps to the stored `Chunk.content`.
`similarity_score` is calculated as `1 - cosine_distance` and is not clamped to
the 0-1 range. Search returns an empty array when no embedded chunks match,
including when the project ID is unknown. The document-list response does not
include `is_indexed`, and there
is no document-detail or indexing-status endpoint.

## Test source

The current test file contains 13 test functions. Four vector-search tests
require Postgres+pgvector and skip when the database is unavailable. Consult
the verification report for whether tests were run during a particular audit;
this reference makes no claim that they pass.
