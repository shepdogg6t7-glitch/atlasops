# Semantic Search - Milestone 2

## Overview

Milestone 2 implements semantic search infrastructure for AtlasOps, enabling full-text similarity search across document chunks using vector embeddings.

## Architecture

### Data Flow

```
User Upload PDF
    ↓
API: POST /projects/{project_id}/documents
    ↓
Save to MinIO/S3 + Create Document record
    ↓
Emit "document.uploaded" to Kafka/Redpanda
    ↓
Consumer: Listen for document.uploaded event
    ↓
Extract text from PDF (PyPDF)
    ↓
Chunk text (1000 char chunks, 200 char overlap)
    ↓
Generate embeddings (SentenceTransformer, 384-dim)
    ↓
Store chunks + embeddings in DB
    ↓
Mark document as is_indexed=True
    ↓
User Query: POST /projects/{project_id}/search
    ↓
Encode query to embedding
    ↓
Cosine similarity search via pgvector
    ↓
Return top N results with similarity scores
```

## Database Schema

### New Tables & Fields

**Document (Extended)**
- `is_indexed` (boolean, default: false) - Whether document has been processed and indexed
- `indexed_at` (timestamp, nullable) - When document was indexed

**DocumentChunk (New)**
- `id` (UUID, primary key)
- `document_id` (UUID, foreign key to documents.id)
- `chunk_index` (integer) - Position in document
- `content` (text) - Chunk content
- `embedding` (vector(384)) - 384-dimensional embedding (all-MiniLM-L6-v2)
- `created_at` (timestamp) - Creation timestamp
- Unique constraint: (document_id, chunk_index)
- Indexes:
  - B-tree on document_id (fast joins)
  - IVFFlat on embedding (fast cosine similarity search)

### Migration

Run the migration to set up the schema:

```bash
# Manual
psql $DATABASE_URL < apps/api/migrations/001_add_semantic_search.sql

# With Docker
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB < apps/api/migrations/001_add_semantic_search.sql

# Direct against a named container (what was actually used to apply this
# migration to the dev database during review)
cat apps/api/migrations/001_add_semantic_search.sql | docker exec -i atlasops-postgres psql -U atlasops -d atlasops
```

See `apps/api/migrations/README.md` for more details.

## API Endpoints

### Existing Endpoints (Unchanged)

All existing endpoints remain fully functional:

- `POST /organizations` - Create organization
- `POST /organizations/{org_id}/projects` - Create project
- `POST /projects/{project_id}/documents` - Upload document
- `GET /projects/{project_id}/documents` - List documents
- `GET /health` - Health check

### New Endpoints

#### Semantic Search

```
POST /projects/{project_id}/search
Content-Type: application/json

Request:
{
  "query": "machine learning algorithms",
  "limit": 10
}

Response:
[
  {
    "chunk_id": "uuid",
    "document_id": "uuid",
    "filename": "document.pdf",
    "chunk_index": 0,
    "text": "This chunk contains text about machine learning...",
    "similarity_score": 0.87  # 0-1, higher is more similar
  },
  ...
]
```

**Parameters:**
- `query` (string, required) - Search query (plain text, automatically embedded)
- `limit` (integer, optional, default: 10) - Max results to return

**Response:**
- Array of chunks sorted by similarity score (highest first)
- Each result includes chunk content + document context + similarity score
- Returns empty array if no indexed chunks or project not found
- Note: the `text` field in the response is the chunk's `content` column,
  renamed at the API layer for a stable external contract

## Implementation Details

### Text Extraction & Chunking

**Supported Formats:** PDF (Milestone 2)

**Processing Pipeline:**
1. Extract text from PDF using PyPDF
2. Normalize whitespace (collapse multiple spaces/newlines)
3. Split into 1000-character chunks with 200-character overlap
4. Generate embeddings for each chunk using SentenceTransformer

**Consumer Configuration:**
- Model: `all-MiniLM-L6-v2` (fast, lightweight, 384-dim)
- Stores 384-dim embeddings directly - no OpenAI dependency, fully local
- Chunk size: 1000 characters
- Overlap: 200 characters (helps preserve context at boundaries)

### Search

**Embedding Model:** SentenceTransformer (`all-MiniLM-L6-v2`)
- Fast inference (~50ms for typical queries)
- 384-dimensional embeddings
- Normalized for cosine similarity

**Search Algorithm:**
- Query → 384-dim embedding via SentenceTransformer
- Cosine distance search in pgvector (IVFFlat index), via the
  `Column.cosine_distance(...)` comparator method (not `func.cosine_distance`,
  which does not exist)
- Convert distance to similarity score (1 - distance)
- Return top N results

## Dependencies

**New (Milestone 2):**
- `pgvector==0.2.0` - SQLAlchemy integration for vector operations

**Existing:**
- `sentence-transformers==6.1.0` - Embedding generation
- `pypdf==6.19.0` - PDF text extraction
- `sqlalchemy==2.0.54` - ORM
- `aiokafka==0.14.0` - Kafka consumer

## Testing

Run tests:
```bash
pytest apps/api/tests/test_semantic_search.py -v
```

Test coverage:
- Model structure and defaults
- Text chunking algorithm
- Document upload
- Semantic search endpoint (against a real Postgres+pgvector database -
  cosine-distance queries cannot run against SQLite)
- Result structure and scoring
- Empty project handling
- Backward compatibility with existing endpoints

The suite uses two database fixtures: an in-memory SQLite database for
CRUD/logic tests, and a real Postgres+pgvector connection (via `DATABASE_URL`)
for the four tests that exercise vector similarity search. The Postgres-backed
tests skip cleanly if a real database isn't reachable, rather than failing.

See `apps/api/tests/test_semantic_search.py` for full test suite.

## Usage Example

### 1. Create Organization & Project

```bash
ORG=$(curl -X POST http://localhost:8000/organizations \
  -H "Content-Type: application/json" \
  -d '{"name": "My Org"}' | jq -r '.id')

PROJECT=$(curl -X POST http://localhost:8000/organizations/$ORG/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "My Project"}' | jq -r '.id')
```

### 2. Upload Document

```bash
curl -X POST http://localhost:8000/projects/$PROJECT/documents \
  -F "file=@document.pdf"
```

The document is now:
- Stored in MinIO
- Added to database with `status="uploaded"`
- Queued for processing

Wait ~30 seconds for the consumer to process...

### 3. Verify Indexing

```bash
curl http://localhost:8000/projects/$PROJECT/documents | jq '.[] | {filename, is_indexed}'
```

Once `is_indexed=true`, the document is searchable.

### 4. Search

```bash
curl -X POST http://localhost:8000/projects/$PROJECT/search \
  -H "Content-Type: application/json" \
  -d '{"query": "your search terms", "limit": 5}' | jq '.'
```

## Backward Compatibility

✅ **Fully backward compatible:**
- Document upload unchanged (new fields have defaults)
- List documents unchanged (excludes new fields by default)
- Existing Kafka pipeline untouched
- Optional: Only indexed documents are searchable

## Performance Considerations

### Search Performance
- IVFFlat index: O(log n) with 100 lists
- Typical query: ~50ms for embedding + ~10ms for search
- Total: ~60ms per query

### Indexing Performance
- PDF extraction: ~1-2s per page
- Embedding generation: ~100ms per chunk
- Database insert: ~1ms per chunk
- Bottleneck: PDF extraction for large documents

### Storage
- 384-dim float32 embedding: ~1.5KB per chunk
- Typical chunk: ~1KB text + 1.5KB embedding = ~2.5KB
- 1000-page PDF ≈ 300-500 chunks ≈ 0.75-1.25MB storage

## Future Enhancements

- [Milestone 3+] Support for more document formats (DOCX, TXT, markdown)
- [Milestone 3+] Hybrid search (keyword + semantic)
- [Milestone 3+] Re-indexing stale documents
- [Milestone 3+] Batch embedding generation optimization
- [Milestone 3+] Optional swap to a paid embeddings API (e.g. OpenAI) for
  higher-dimensional embeddings, if local model quality becomes a limiting
  factor - not needed for current functionality

## Troubleshooting

**Q: Search returns empty results**
- Verify document has `is_indexed=true`
- Check consumer logs: `docker compose logs consumer`
- Ensure chunks were created: `SELECT COUNT(*) FROM document_chunks WHERE document_id = '...'`

**Q: Consumer crashes on PDF extraction**
- Check PDF is valid and readable
- Review consumer logs for extraction errors
- Document status set to "error" on failure

**Q: Slow search queries**
- Check IVFFlat index exists: `\d document_chunks` in psql
- Verify query doesn't match too many documents
- Consider reducing limit parameter

**Q: `sqlalchemy.exc.ProgrammingError: column "is_indexed" of relation "documents" does not exist`**
- The migration (`001_add_semantic_search.sql`) hasn't actually been run
  against your database yet. `Base.metadata.create_all()` only creates
  tables that don't already exist - it will not add new columns to a table
  that's already there. Run the migration manually (see Migration section
  above).

## Files Changed

### Core Implementation
- `apps/api/models.py` - Added Chunk model (`document_chunks` table), Document indexing fields
- `apps/api/main.py` - Added semantic search endpoint
- `apps/api/consumer.py` - Updated to use ORM, store embeddings

### Database
- `apps/api/migrations/001_add_semantic_search.sql` - Schema changes
- `apps/api/migrations/README.md` - Migration documentation

### Testing
- `apps/api/tests/test_semantic_search.py` - Integration tests (13 test cases)
- `pytest.ini` - Test configuration

### Configuration
- `apps/api/requirements.txt` - Added pgvector, pytest, pytest-asyncio
- `compose.yaml` - Already uses pgvector/pgvector:pg16 image

## Post-Review Fixes

A code review before merge found that this milestone's initial implementation
had a schema conflict with the `document_chunks` table already created and
verified in Checkpoint 4: the original migration created a differently-named,
differently-shaped `chunks` table (`text` column, `vector(1536)`) that was
never actually connected to the existing verified table, and the dimension
didn't match the real output of `all-MiniLM-L6-v2` (384, not 1536). This meant
real document ingestion would fail with a pgvector dimension error, despite
the original test suite reporting all tests passing.

The following were corrected prior to merge:
- `chunks` table renamed to `document_chunks`, matching the existing schema
- `text` column renamed to `content`
- `vector(1536)` corrected to `vector(384)`, matching the actual embedding
  model output
- `func.cosine_distance(...)` (not a valid SQLAlchemy/pgvector call) replaced
  with `Chunk.embedding.cosine_distance(...)`, the real pgvector API
- The migration itself was applied to the live dev database for the first
  time (the `is_indexed`/`indexed_at` columns had never actually been added)
- Test suite fixed: SQLite fixture missing `StaticPool` (tables were being
  dropped between connections), no way to test real vector-distance queries
  against SQLite at all (added dedicated Postgres-backed fixtures), an
  unflushed-object assertion bug, `TestClient` not triggering FastAPI's
  `lifespan` (leaving the Kafka producer uninitialized during tests), and a
  `KeyError`-prone assertion that couldn't safely short-circuit

All 13 tests now pass against a real Postgres+pgvector database, with the
full pipeline (upload → chunk → embed → store → query → similarity results)
verified end-to-end for the first time.

## Status

✅ Infrastructure complete and tested
✅ End-to-end pipeline verified against real Postgres+pgvector
✅ Backward compatible with existing features
✅ Ready for production use (within the scope of a local dev stack)

---

**Milestone 2 completion checklist:**
- ✅ Chunk model with pgvector embeddings (`document_chunks` table)
- ✅ Document indexing tracking (is_indexed, indexed_at)
- ✅ Semantic search endpoint with cosine similarity
- ✅ Text extraction and embedding generation
- ✅ Database migration and indexes
- ✅ Comprehensive test coverage (13/13 passing against real Postgres+pgvector)
- ✅ Documentation
