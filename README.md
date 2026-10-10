# AtlasOps

Open-source, self-hostable AI document intelligence platform. Upload a document corpus, index it with semantic embeddings, and query it in natural language. Semantic indexing runs locally; optional Gemini answers send the question and retrieved document excerpts to Google's API.

## What It Does

- Ingests PDFs into per-project corpora, stored in S3-compatible object storage
- Extracts text, chunks it with overlap, and generates 384-dimensional vector embeddings
- Indexes chunks in Postgres with the pgvector extension for cosine-similarity search
- Serves semantic search queries over HTTP with ranked results and similarity scores
- Answers questions about retrieved document passages using the Gemini API free tier
- Uses an event-driven ingestion pipeline (Kafka-compatible Redpanda) so upload and indexing are decoupled

## Architecture

Upload, retrieval, and question-answering share a Postgres + pgvector backend.

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

Question-answering path:
  Client → POST /projects/{id}/ask
         → retrieve relevant chunks using local embeddings + pgvector
         → send question + excerpts to Gemini API (server-side key)
         → return answer + cited source chunks
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
| Local services | Docker Compose |
| Frontend hosting | Vercel (FastAPI and data services are separate) |

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
the SentenceTransformer model downloads automatically (~90MB). Configure the
Gemini key on the API server to enable document question-answering; the web app
defaults to `http://localhost:8000` and can be pointed at another API with
`NEXT_PUBLIC_API_BASE_URL`.

Run `python -m apps.api.consumer` from another terminal to process uploaded
documents, and run `npm install && npm run dev` from `apps/web` to start the
frontend.

## API Endpoints

- `GET /health` — health check
- `POST /organizations` — create an organization
- `POST /organizations/{org_id}/projects` — create a project
- `POST /projects/{project_id}/documents` — upload a PDF; creates the document record and emits an ingestion event
- `GET /projects/{project_id}/documents` — list documents (responses do not include `is_indexed`)
- `POST /projects/{project_id}/search` — semantic search; returns top-N chunks with similarity scores
- `POST /projects/{project_id}/ask` — retrieve matching chunks and return a Gemini-generated answer with source excerpts

Ask request (the optional `limit` is 1–10 and defaults to 5):

```http
POST /projects/{project_id}/ask
Content-Type: application/json

{"question": "What does the report say about reliability?", "limit": 5}
```

The response contains an `answer` string and a `sources` array with the matched
chunk metadata and excerpt text.

There is no document-detail or indexing-status endpoint. Search returns an empty
array when the project ID does not match a project, as well as when no matching
chunks are available. See [MILESTONE_2.md](MILESTONE_2.md) for request/response
schemas and usage examples.

## Free LLM API setup

AtlasOps uses the Gemini API with the pinned model `gemini-3.5-flash-lite`.
Create an API key in [Google AI Studio](https://aistudio.google.com/) and set
these variables **only on the FastAPI server**:

```dotenv
LLM_PROVIDER=gemini
LLM_API_KEY=your-google-ai-studio-key
LLM_MODEL=gemini-3.5-flash-lite
LLM_TIMEOUT_SECONDS=30
```

The key is never sent to the browser. The answer endpoint embeds the question
locally, retrieves up to five relevant passages from the selected project, and
sends the question and those excerpts to Gemini. It returns the generated
answer and the source passages. If there are no matching chunks, it returns a
no-results answer without calling Gemini. Gemini free-tier access has changing
quotas and terms; check Google's [pricing](https://ai.google.dev/gemini-api/docs/pricing)
and [terms](https://ai.google.dev/gemini-api/terms) before use. Under the
current free-tier terms, submitted content may be used to improve Google's
products. Do not enable this for confidential documents unless that data
handling is acceptable.

## Zero-cost-style deployment

Vercel is the simplest fit for this Next.js frontend. Set the Vercel project
root to `apps/web` and configure `NEXT_PUBLIC_API_BASE_URL` to the public HTTPS
URL of the FastAPI service. On the API host, set `CORS_ORIGIN` to the deployed
frontend's exact origin, plus the database, S3-compatible storage, Redpanda,
and Gemini environment variables described above. Never set the Gemini key as
a `NEXT_PUBLIC_*` variable.

This deploys the frontend only. AtlasOps still needs a reachable FastAPI
backend, Postgres with pgvector, S3-compatible object storage, Redpanda, and a
running document consumer; a frontend deployment does not replace those
services. Free quotas, sleep limits, storage limits, and service terms vary
and can change. Verify that your chosen providers can run the API and
persistent consumer before exposing the app publicly. The current API also
has no authentication or rate limiting; add access controls before public use
to prevent unauthorized uploads and Gemini quota abuse.

## Testing

```bash
pytest
```

Test configuration is in `pytest.ini` (asyncio auto mode, tests under `apps/api/tests/`). Run the Gemini client unit tests with `python -m unittest apps.api.tests.test_llm`. Existing Postgres-backed tests require `DATABASE_URL`. [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md) covers a previous documentation audit; it is not a deployment-readiness report.

## Project Status

- **Milestone 1** — Foundation: API, database schema, object storage, project and document models — done
- **Milestone 2** — Semantic search: pgvector indexing, embedding pipeline, ingestion worker, search endpoint — done
- **LLM Q&A** — Gemini-backed answers grounded in retrieved document chunks — implemented; free-tier limits apply
- **Milestone 3** — Planned

## Documentation

- [`MILESTONE_2.md`](MILESTONE_2.md) — full Milestone 2 design and implementation
- [`examples/`](examples/) — sample documents and evaluation dataset

## License

Apache 2.0 — see [LICENSE](LICENSE).
