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
- **002_authentication.sql**: Adds the users and organization membership tables required for authentication and tenant authorization

Organizations that existed before authentication have no owner mapping and are intentionally inaccessible to new accounts. After registering the intended owner, an operator can grant the matching membership by organization UUID, for example:

```sql
INSERT INTO organization_memberships (user_id, organization_id, role)
SELECT id, 'replace-with-organization-uuid'::uuid, 'owner'
FROM users
WHERE email = 'owner@example.com'
ON CONFLICT DO NOTHING;
```

Only assign an existing organization to the account authorized to access its data.
