# Bozza scaletta slide (demo / esame)

1. **Titolo e obiettivo** — “A Fragile Balance of Power”: pipeline sismica distribuita, repliche e tolleranza ai guasti.
2. **Contesto** — Simulator container (sensori WS + SSE control); vincoli: fan-out, niente duplicate logic “magica” sul broker.
3. **Architettura** — Diagramma da `architecture.md`: broker → N processing → PostgreSQL; gateway unico; dashboard.
4. **Broker** — Discovery HTTP + N WebSocket; POST parallelo a `/internal/ingest`; parametri ambiente (`ALL_SENSORS`, `PROCESSING_URLS`).
5. **Processing** — Finestra scorrevole, FFT, bande di classificazione, `dedup_key`; idempotenza `ON CONFLICT DO NOTHING`.
6. **Fault injection** — SSE `SHUTDOWN`; una replica esce; broker + altra replica + gateway ancora utilizzabili.
7. **Gateway** — `/api/events`, SSE stream, round-robin + failover verso RAM repliche; CORS per il front-end.
8. **Dashboard** — Polling + EventSource; tab DB vs tab RAM (perché possono differire).
9. **Demo live** — `docker compose up`, aprire 3000 e 8090/health; opzionale `curl` su `/api/events`.
10. **Chiusura** — User stories e schema eventi in `input.md`; limiti e possibili estensioni (metriche, auth).
