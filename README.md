# AtlasOps

Open-source, self-hostable AI document intelligence platform. Upload a document corpus, index it with semantic embeddings, and query it in natural language — all running on your own infrastructure, with no data leaving your network.

## What It Does

- Ingests PDFs into per-project corpora, stored in S3-compatible object storage
- Extracts text, chunks it with overlap, and generates 384-dimensional vector embeddings
- Indexes chunks in Postgres with the pgvector extension for cosine-similarity search
- Serves semantic search queries over HTTP with ranked results and similarity scores
- Uses an event-driven ingestion pipeline (Kafka-compatible Redpanda) so upload and indexing are decoupled

## Architecture

Upload and query are separate paths that share a Postgres + pgvector backend.

```
Upload path:
  Client → POST /projects/{id}/documents
         → MinIO (S3) + Document record
         → emit document.uploaded to Redpanda
         → ingestion worker consumes event
         → PyPDF extract → chunk (1000c/200 overlap)
         → SentenceTransformer embed (384-dim)
         → store chunks + vectors in Postgres

Query path:
  Client → POST /projects/{id}/search
         → encode query to 384-dim vector
         → cosine similarity via pgvector
         → return top-N chunks with scores
```

## Stack

| Component | Technology |
|---|---|
| API | Python 3, FastAPI, SQLAlchemy, Pydantic |
| Database | Postgres 16 + pgvector |
| Object storage | MinIO (S3-compatible) |
| Event bus | Redpanda (Kafka-compatible) |
| Cache | Redis 7 |
| Embeddings | SentenceTransformer (384-dim) |
| PDF parsing | PyPDF, 1000-char chunks, 200-char overlap |
| Frontend | Next.js |
| Testing | pytest + pytest-asyncio |
| Deployment | Docker Compose |

## Quickstart

Backing services run in Docker; the API runs locally against them.

```bash
git clone https://github.com/shepdogg6t7-glitch/atlasops.git
cd atlasops
cp .env.example .env             # edit values if needed
docker compose up -d             # Postgres, Redis, MinIO, Redpanda
python -m venv .venv && source .venv/bin/activate
pip install -r apps/api/requirements.txt
uvicorn apps.api.main:app --reload
```

The API is then available at http://localhost:8000. On first run,
the SentenceTransformer model downloads automatically (~90MB).

## API Endpoints

- `POST /projects/{project_id}/documents` — upload a PDF; creates the document record and emits an ingestion event
- `GET /projects/{project_id}/documents/{document_id}` — check indexing status (`is_indexed`)
- `POST /projects/{project_id}/search` — semantic search; returns top-N chunks with similarity scores

See [MILESTONE_2.md](MILESTONE_2.md) for the full endpoint specification, request/response schemas, and usage examples.

## Testing

```bash
pytest
```

Test configuration is in `pytest.ini` (asyncio auto mode, tests under `apps/api/tests/`). A full verification report from the Milestone 2 review is in [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md); the milestone-specific report is in [MILESTONE_2_VERIFICATION.md](MILESTONE_2_VERIFICATION.md).

## Project Status

- **Milestone 1** — Foundation: API, database schema, object storage, project and document models — done
- **Milestone 2** — Semantic search: pgvector indexing, embedding pipeline, ingestion worker, search endpoint — done
- **Milestone 3** — Planned

## Documentation

- [`docs/adr/`](docs/adr/) — architecture decision records
- [`docs/architecture/`](docs/architecture/) — system architecture notes
- [`docs/operations/`](docs/operations/) — operational runbooks
- [`docs/security/`](docs/security/) — security posture and threat model
- [`MILESTONE_2.md`](MILESTONE_2.md) — full Milestone 2 design and implementation
- [`examples/`](examples/) — sample documents and evaluation dataset

## License

Apache 2.0 — see [LICENSE](LICENSE).

