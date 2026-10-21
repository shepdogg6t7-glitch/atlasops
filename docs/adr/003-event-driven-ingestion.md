# ADR-003: Event-Driven Ingestion via Redpanda

## Status
Accepted

## Context
Document upload and indexing are decoupled so the upload API returns quickly while indexing (PDF extraction, chunking, embedding) happens asynchronously.

## Decision
Use Redpanda (Kafka-compatible) as the event bus. The API emits `document.uploaded` events; a standalone consumer processes them.

## Consequences
- Positive: Upload API remains responsive; indexing failures don't block uploads; consumer can be scaled independently
- Negative: Eventual consistency — documents are not immediately searchable after upload

## Related
docs/architecture/data-flow.md
