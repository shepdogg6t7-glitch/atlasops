# AtlasOps Threat Model

## Assets

| Asset | Sensitivity | Protection |
|-------|-------------|------------|
| Uploaded PDF documents | High (customer data) | MinIO + loopback binding, disk encryption at host |
| Document chunks + embeddings | High (derived customer data) | PostgreSQL + pgvector, loopback binding |
| User credentials | High | Argon2id hashes in PostgreSQL |
| JWT signing secret | Critical | `JWT_SECRET` env var, 32+ chars, never logged |
| LLM/embedding API keys | Critical | `.env` on API host only, not in frontend or logs |

## Threats and Mitigations

| Threat Actor | Threat | Impact | Likelihood | Mitigation |
|--------------|--------|--------|------------|------------|
| Unauthenticated attacker | Register account when registration open | Unauthorized org creation | Medium | `ALLOW_REGISTRATION=false` default |
| Unauthenticated attacker | Brute-force login | Account takeover | Medium | Rate limiting (10/min), Argon2id, 12+ char passwords |
| Authenticated user | Access another org's project | Data leakage across tenants | Low | Organization membership check on every `/projects` and `/organizations` endpoint |
| Network attacker | Intercept API traffic | Credential/document theft | Medium | TLS termination at reverse proxy; loopback-only defaults |
| Malicious file upload | Non-PDF or oversized file | DoS, code execution | Low | PDF magic-byte check, 25 MB limit, multipart overhead check |
| Insider / compromised account | Export all documents | Data exfiltration | Medium | Per-user rate limiting, organization isolation, audit via logs |
| Service outage | Redis down for rate limiting | All limited requests get 503 | Medium | Fails closed by design |
| LLM provider compromise | API key leakage | Unauthorized LLM usage, cost | Low | Keys stored in `.env` only, restricted file permissions |

## Data Flow Boundaries

1. **Client → API**: HTTPS (production), HTTP (dev localhost)
2. **API → PostgreSQL**: Loopback-only Docker network
3. **API → MinIO**: Loopback-only Docker network
4. **API → Redpanda**: Loopback-only Docker network
5. **API → LLM provider**: Outbound HTTPS (only when LLM Q&A enabled)

## Assumptions

- Host OS and Docker daemon are patched and hardened
- Underlying disk/volume encryption is enabled at the infrastructure layer
- Reverse proxy (nginx, traefik, cloud load balancer) handles TLS termination
- `JWT_SECRET` is generated with `secrets.token_urlsafe(48)` or equivalent
