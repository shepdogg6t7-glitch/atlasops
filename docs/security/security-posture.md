# AtlasOps Security Posture

## Scope

This document describes the security posture of the AtlasOps self-hosted document intelligence platform. It covers the FastAPI backend, PostgreSQL + pgvector database, MinIO object storage, Redpanda event bus, Redis cache, and Next.js frontend.

## Deployment Model

AtlasOps is designed for self-hosted, private-infrastructure deployment. All backing services bind to loopback-only ports by default (via Docker Compose). No data leaves the customer's network unless explicitly configured.

## Security Controls Implemented

| Area | Control | Implementation |
|------|---------|----------------|
| Authentication | Password hashing | Argon2id via argon2-cffi, 12+ char minimum |
| Authentication | Session tokens | JWT bearer tokens, 30-minute expiry, configurable secret |
| Authorization | Organization isolation | Project access checked against user's organization membership |
| Authorization | Registration gating | `ALLOW_REGISTRATION` on/off switch, defaults to false |
| Input validation | File type | PDF magic-byte validation, not extension-only |
| Input validation | File size | 25 MB default limit, multipart overhead accounted |
| Input validation | Filename sanitization | Path traversal, control character, and Unicode normalization stripping |
| Rate limiting | Per-user/IP | slowapi with Redis-backed storage, fails closed on Redis outage |
| Network | CORS | Configurable `CORS_ORIGIN`, localhost-only by default |
| Secrets | JWT signing key | Required `JWT_SECRET` (32+ chars), no dev fallback key |
| Secrets | API keys | LLM/embedding keys in `.env` only, never committed or logged |
| Transport | TLS | Required for production exposure; HTTPS enforcement at reverse proxy |

## What Is Not In Scope

- Multi-tenant SaaS hosting (AtlasOps is self-hosted)
- SSO/OIDC integration (email/password only)
- End-to-end encryption of documents at rest (relies on underlying storage/disk encryption)
- SIEM integration (logs are stdout/stderr; forward via your log aggregator)
