# Architecture diagram (Project-42)

## Logical view

```mermaid
flowchart LR
  subgraph Sim["Simulator (provided)"]
    DEV["/api/devices"]
    WS["WebSocket /api/device/.../ws"]
    SSE["SSE /api/control"]
  end

  B[Broker]
  P1[Processing 1]
  P2[Processing 2]
  DB[(PostgreSQL)]
  G[Gateway]
  W[Web dashboard]

  DEV --> B
  WS --> B
  B --> P1
  B --> P2
  SSE --> P1
  SSE --> P2
  P1 --> DB
  P2 --> DB
  G --> DB
  G --> P1
  G --> P2
  W --> G
```

### Flows

1. **Ingestion**: the broker opens N WebSockets to the simulator and **fan-out** HTTP `POST /internal/ingest` to every replica.
2. **Processing**: each replica keeps a per-sensor window, FFT, classification; writes to the DB with `ON CONFLICT DO NOTHING`.
3. **Fault injection**: SSE `SHUTDOWN` stops **one** replica at a time.
4. **Presentation**: the browser talks only to the **gateway** (REST + SSE); the gateway queries the DB and, with failover, replicas for in-RAM data.

*(Export to PNG from GitHub / Mermaid Live Editor for slides.)*
