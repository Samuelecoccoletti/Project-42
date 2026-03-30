# Slide deck draft (demo / exam)

1. **Title and goal** — “A Fragile Balance of Power”: distributed seismic pipeline, replicas, fault tolerance.
2. **Context** — Simulator container (sensor WS + SSE control); constraints: fan-out, no “magic” duplicate logic on the broker.
3. **Architecture** — Diagram from `architecture.md`: broker → N processing → PostgreSQL; single gateway; dashboard.
4. **Broker** — HTTP discovery + N WebSockets; parallel `POST` to `/internal/ingest`; env (`ALL_SENSORS`, `PROCESSING_URLS`).
5. **Processing** — Sliding window, FFT, classification bands, `dedup_key`; idempotency `ON CONFLICT DO NOTHING`.
6. **Fault injection** — SSE `SHUTDOWN`; one replica exits; broker + other replica + gateway still usable.
7. **Gateway** — `/api/events`, SSE stream, round-robin + failover to replica RAM; CORS for the front-end.
8. **Dashboard** — Polling + EventSource; DB tab vs RAM tab (they can differ).
9. **Live demo** — `docker compose up`, open 3000 and 8090/health; optional `curl` on `/api/events`.
10. **Closing** — User stories and event schema in `input.md`; limits and possible extensions (metrics, auth).
