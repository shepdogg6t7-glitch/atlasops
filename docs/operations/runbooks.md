# AtlasOps Operational Runbooks

## Runbook: Deploy Backing Services

### Prerequisites
- Docker and Docker Compose installed
- `docker compose` available

### Steps
```bash
cd /path/to/atlasops
docker compose up -d
```

### Verify
- `docker compose ps` shows all containers running
- `curl http://localhost:8000/health` returns `{"status": "ok"}`

### Rollback
```bash
docker compose down
```

---

## Runbook: Run Database Migration

### Prerequisites
- PostgreSQL running and reachable via `DATABASE_URL`
- `psql` client installed

### Steps
```bash
psql "$DATABASE_URL" < apps/api/migrations/001_add_semantic_search.sql
```

### Verify
- `\d documents` shows `is_indexed` and `indexed_at` columns
- `\d document_chunks` shows the chunks table with `embedding vector(384)`

---

## Runbook: Start the API

### Prerequisites
- Backing services running
- Virtual environment activated
- `pip install -r apps/api/requirements.txt` completed
- `JWT_SECRET` set (32+ chars)

### Steps
```bash
uvicorn apps.api.main:app --reload
```

### Verify
- `curl http://localhost:8000/health` returns `{"status": "ok"}`

---

## Runbook: Start the Ingestion Consumer

### Prerequisites
- Backing services running (Redpanda, MinIO, PostgreSQL)
- Virtual environment activated

### Steps
```bash
python apps/api/consumer.py
```

### Verify
- Consumer log shows "Consumer started, listening on..."
- Uploaded documents transition from `uploaded` to `processed` within ~30s

---

## Runbook: Rotate JWT Secret

### When
- Suspected key compromise
- Periodic credential rotation

### Steps
1. Generate new secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
2. Update `JWT_SECRET` in `.env`
3. Restart the API: all existing bearer tokens become invalid; users must re-login

### Verify
- Old tokens return 401
- New login succeeds

---

## Runbook: Respond to Rate-Limit Storage Outage

### Symptom
- Limited endpoints return 503 with "Rate-limit storage is unavailable"

### Cause
- Redis unavailable and `RATE_LIMIT_STORAGE_URI` points to Redis

### Mitigation
1. Restore Redis, or
2. Switch to in-memory storage: `RATE_LIMIT_STORAGE_URI=memory://` (per-process counters only)
3. Restart the API

> The API fails closed: when Redis is down, limited requests receive 503 until it recovers.

---

## Runbook: Backup and Restore

### Backup
1. PostgreSQL: `pg_dump "$DATABASE_URL" > backup.sql`
2. MinIO: Use `mc` or S3 sync to back up the `atlasops-documents` bucket

### Restore
1. `psql "$DATABASE_URL" < backup.sql`
2. Restore MinIO bucket contents
3. Restart API and consumer
