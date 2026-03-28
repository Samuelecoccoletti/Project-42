# Student documentation — Project42

Technical description of the deployed system (containers, ports, persistence, APIs). User stories and backlog are in `input.md` only.

## Contents

1. [System overview](#1-system-overview)  
2. [Container and port map](#2-container-and-port-map)  
3. [Shared database schema](#3-shared-database-schema)  
4. [Containers](#4-containers)  
5. [Run and URLs](#5-run-and-urls)

---

## 1. System overview

The stack ingests simulated seismic data from the course **simulator** (WebSocket per sensor). A **broker** discovers sensors over REST, subscribes to each stream, and fans out every sample over HTTP to **two processing replicas**. Each replica keeps a per-sensor sliding window, runs FFT, classifies by frequency band, and writes to **PostgreSQL** using an idempotent `dedup_key`. Replicas subscribe to the simulator SSE control API and exit on `SHUTDOWN`. A **gateway** exposes read APIs, SSE for new events, replica health, and proxies to processing with round-robin and failover. The **web** container serves the React dashboard and proxies `/api` to the gateway so the browser uses one origin on port 3000.

---

## 2. Container and port map

| Container name | Service | Host port | Container port | Notes |
|----------------|---------|-----------|------------------|-------|
| seismic-db | PostgreSQL 16 | 5432 (optional) | 5432 | Volume `pgdata` |
| seismic-simulator | Course simulator | 8080 | 8080 | Do not modify image |
| seismic-broker | Broker worker | — | — | No listening ports |
| seismic-processing-1 | Processing replica 1 | 8001 | 8000 | Same image as replica 2 |
| seismic-processing-2 | Processing replica 2 | 8002 | 8000 | |
| seismic-gateway | Gateway API | 8090 | 8090 | |
| seismic-web | nginx + SPA | 3000 | 80 | Proxies `/api` → gateway |

Compose file: `source/docker-compose.yml`.

---

## 3. Shared database schema

Schema file: `source/db/init.sql`. Processing replicas insert into this table; the gateway reads it.

**Table `detected_events`**

| Column | Type | Constraints / notes |
|--------|------|---------------------|
| id | BIGSERIAL | Primary key |
| dedup_key | CHAR(64) | NOT NULL, UNIQUE — idempotency across replicas |
| sensor_id | TEXT | NOT NULL |
| classification | TEXT | NOT NULL |
| dominant_frequency_hz | DOUBLE PRECISION | NOT NULL |
| energy | DOUBLE PRECISION | Nullable |
| detected_at | TIMESTAMPTZ | NOT NULL |
| replica_id | TEXT | Nullable |
| created_at | TIMESTAMPTZ | NOT NULL, default NOW() |

Indexes: `detected_at` (desc), `sensor_id`.

---

## 4. Containers

### 4.1 seismic-db

- **Role:** Shared relational store for classified events.
- **Persistence:** Strong — data on named volume `pgdata` until volume removed or `docker compose down -v`.
- **Connections:** Gateway and both processing replicas connect to `db:5432` (credentials from compose).

**Microservice: postgresql (database)**  
PostgreSQL 16 Alpine; user/database `seismic`. Uniqueness on `dedup_key`; application uses `INSERT … ON CONFLICT (dedup_key) DO NOTHING`.

---

### 4.2 seismic-simulator

- **Role:** Provided image `seismic-signal-simulator:multiarch_v1` — sensor WebSocket streams, device discovery REST, SSE fault injection (`SHUTDOWN` to one listener).
- **Persistence:** Not part of the team persistence deliverable.
- **Connections:** Broker uses HTTP/WebSocket to `simulator:8080`; replicas use SSE `GET /api/control`. Host: `http://localhost:8080` for `/health` and OpenAPI.

**Microservice: seismic-signal-simulator (provided backend)**

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/health` | Health |
| GET | `/api/devices/` | Sensors and WebSocket paths |
| GET | `/openapi.json`, `/docs` | API contract |
| WebSocket | `/api/device/{sensor_id}/ws` | Sample stream (timestamp, mm/s) |
| GET (SSE) | `/api/control` | control-open, heartbeat, command |

Env examples in compose: `SAMPLING_RATE_HZ`, `AUTO_SHUTDOWN_*`.

---

### 4.3 seismic-broker

- **Role:** Python async worker — discovery, one WebSocket per sensor, parallel HTTP POST of each sample to all `PROCESSING_URLS`. No FFT, no DB.
- **Ports:** None (client only).
- **Persistence:** None (transient while posting).
- **Connections:** Outbound to `simulator:8080` and to `processing-1:8000`, `processing-2:8000` (`POST /internal/ingest`).

**Microservice: broker-ingest (backend, no HTTP server)**  
Stack: Python 3, httpx, websockets. Env: `SIMULATOR_BASE_URL`, `PROCESSING_URLS`, `ALL_SENSORS`, `MAX_SAMPLES`, `WS_PING_*`. No exposed endpoints.

---

### 4.4 seismic-processing-1 and seismic-processing-2

- **Role:** Two instances of the same image. Ingest from broker, sliding window + FFT + classification, write to PostgreSQL, SSE control loop for `SHUTDOWN`.
- **Differences:** `REPLICA_ID` (1 vs 2) and host port mapping (8001 vs 8002 → 8000 in container).
- **Persistence:** In-memory windows and recent-event buffer (volatile); durable rows in PostgreSQL (see §3).
- **Connections:** Inbound HTTP from broker; outbound asyncpg to `db`, SSE to `simulator`.

**Microservice: processing-api (backend, per replica)**

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/health` | Status, window size, persistence flag |
| POST | `/internal/ingest` | Body: `sensor_id`, `timestamp`, `value` |
| GET | `/internal/recent-events` | Last in-memory events (often via gateway) |

Stack: FastAPI, Uvicorn, NumPy FFT, asyncpg. Notable env: `DATABASE_URL`, `WINDOW_SIZE`, `DEDUP_BUCKET_SEC`, `MIN_CLASSIFY_HZ`, `SIMULATOR_BASE_URL`.

---

### 4.5 seismic-gateway

- **Role:** FastAPI — list/filter events from DB, SSE stream of new rows, aggregate replica health, proxy to processing with failover.
- **Persistence:** Stateless container; data only in PostgreSQL.
- **Connections:** `db:5432`; HTTP to `processing-1:8000` and `processing-2:8000`.

**Microservice: gateway-api (backend)**

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/health` | DB check + count of healthy processing replicas |
| GET | `/api/replicas` | Per-replica reachability and health JSON |
| GET | `/api/events` | Query: `limit`, optional `sensor_id` |
| GET | `/api/events/stream` | SSE batches; optional `sensor_id` |
| GET | `/api/processing/recent-events` | Proxy; header `X-Processing-Replica` |

Env: `DATABASE_URL`, `PROCESSING_URLS`, `CORS_ORIGINS`, `SSE_POLL_SECONDS`.

---

### 4.6 seismic-web

- **Role:** Multi-stage image: Vite/React build + nginx. Serves SPA on port 80; proxies `/api/*` to `gateway:8090` (buffering off for SSE).
- **Persistence:** None (static assets in image).
- **Connections:** Browser → nginx only; nginx → gateway for API.

**Microservice: nginx-static-proxy (reverse proxy)**  
Proxies `/api/*` to gateway; long read timeout for streams.

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/` | Dashboard SPA |
| GET | `/api/*` | Forward to gateway |

**Microservice: dashboard-ui (frontend)**  
React + TypeScript. Docker build: empty `VITE_GATEWAY_URL` → relative `/api/...`. Uses EventSource on `/api/events/stream`, REST for initial events, polling for replicas and in-RAM replica events.

| Page | Description | Related APIs |
|------|-------------|--------------|
| Main dashboard (`/`) | Replica chips, persisted events (SSE + REST), sensor filter, in-RAM events via gateway | gateway → DB and processing |

---

## 5. Run and URLs

From directory `source/`:

1. Import the simulator image (see `scripts/load-simulator-oci.sh` and `README.md`).
2. Run: `docker compose up -d --build`

| Purpose | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| Simulator (docs / health) | http://localhost:8080 |
| Gateway (direct checks) | http://localhost:8090/health |

Product requirements and user stories: **`input.md`**.
