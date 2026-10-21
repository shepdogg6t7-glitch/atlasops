# AtlasOps Deployment Topology

```mermaid
graph TB
    subgraph Internet[Public Internet]
        User[End Users]
    end

    subgraph ReverseProxy[Reverse Proxy / Ingress]
        LB[TLS Termination + CORS]
    end

    subgraph Host[Customer Host / VPC]
        subgraph AppNetwork[Docker Compose Network - loopback bound]
            API[FastAPI API 0.0.0.0:8000]
            Web[Next.js Frontend :3000]
            DB[(PostgreSQL 16 + pgvector 5432)]
            MinIO[(MinIO 9000)]
            RP[(Redpanda 9092)]
            Redis[(Redis 6379)]
            Worker[Ingestion Consumer]
        end
    end

    User -->|HTTPS| LB
    LB -->|HTTP| API
    LB -->|HTTP| Web
    Web --> API

    API --> DB
    API --> MinIO
    API --> RP
    API -.->|optional| Redis

    RP --> Worker
    Worker --> MinIO
    Worker --> DB

    style Host fill:#f9f9f9,stroke:#333,stroke-width:2px
    style AppNetwork fill:#f3e5f5,stroke:#4a148c
    style ReverseProxy fill:#e1f5fe,stroke:#01579b
```

## Port Bindings (Default)

| Service | Port | Binding |
|---------|------|---------|
| FastAPI API | 8000 | localhost only (via reverse proxy) |
| Next.js Frontend | 3000 | localhost only |
| PostgreSQL | 5432 | localhost only (Docker network) |
| MinIO | 9000 | localhost only (Docker network) |
| Redpanda | 9092 | localhost only (Docker network) |
| Redis | 6379 | localhost only (Docker network) |

All service-to-service communication occurs over the Docker Compose internal network, not exposed to the public internet. The reverse proxy is the only ingress point and terminates TLS.
