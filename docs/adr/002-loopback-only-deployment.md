# ADR-002: Self-Hosted, Loopback-Only Deployment

## Status
Accepted

## Context
AtlasOps is positioned as a self-hosted, private-infrastructure platform where no customer data leaves the customer's network.

## Decision
All backing services (PostgreSQL, MinIO, Redpanda, Redis) bind to localhost-only ports via Docker Compose. The API and frontend are accessible only through a customer-managed reverse proxy with TLS.

## Consequences
- Positive: No public exposure of databases or object storage; data sovereignty preserved
- Negative: Customer is responsible for TLS termination, reverse proxy, and host hardening

## Related
docs/architecture/deployment-topology.md, docs/security/threat-model.md
