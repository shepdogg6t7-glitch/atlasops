# Implementation status and documentation audit

**Audit date:** 2026-10-08
**Scope:** Documentation compared with the current API, models, consumer, migration, and test source. This is not a runtime or deployment verification.

## Implementation reflected in the docs

- The embedding model is `all-MiniLM-L6-v2`; vectors have 384 dimensions.
- Chunks are stored in `document_chunks`, with their text in `content`.
- Semantic search is `POST /projects/{project_id}/search`. It accepts `query`
  and optional `limit` (default `10`), and returns an array whose `text` value
  is mapped from `Chunk.content`. `similarity_score` is `1 - cosine_distance`;
  the API does not clamp it to the 0-1 range.
- Search returns an empty array when no rows match, including for an unknown
  project ID; it does not return 404 for that case.
- The document list route is `GET /projects/{project_id}/documents`; it does
  not return `is_indexed`. There is no document-detail or indexing-status
  route.

## Test and deployment status

No tests or deployment checks were run for this documentation audit. The test
source currently contains 13 test functions. Four semantic-search tests use a
Postgres+pgvector fixture and skip if `DATABASE_URL` is unset or the database
cannot be reached. The source does not establish that tests currently pass,
nor does it verify the complete upload-to-indexing worker pipeline end to end.

No production-readiness claim is made. The historical Milestone 2 review notes
are in [MILESTONE_2.md](MILESTONE_2.md); they are not current test results.
