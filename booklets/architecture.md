# Diagramma architettura (Project-42)

## Vista logica

```mermaid
flowchart LR
  subgraph Sim["Simulatore (fornito)"]
    DEV["/api/devices"]
    WS["WebSocket /api/device/.../ws"]
    SSE["SSE /api/control"]
  end

  B[Broker]
  P1[Processing 1]
  P2[Processing 2]
  DB[(PostgreSQL)]
  G[Gateway]
  W[Dashboard web]

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

### Flussi

1. **Ingestione**: broker apre N WebSocket verso il simulatore e fa **fan-out** HTTP `POST /internal/ingest` verso ogni replica.
2. **Elaborazione**: ogni replica mantiene finestra per sensore, FFT, classificazione; scrive su DB con `ON CONFLICT DO NOTHING`.
3. **Fault injection**: SSE `SHUTDOWN` chiude **una** replica alla volta.
4. **Presentazione**: il browser parla solo con **gateway** (REST + SSE); il gateway interroga DB e, con failover, le repliche per dati in RAM.

*(Esportare in PNG da GitHub / Mermaid Live Editor per le slide.)*
