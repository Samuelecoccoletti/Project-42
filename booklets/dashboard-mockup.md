# SEISMIC dashboard — lo-fi mockup

The four-block sketch layout **matches** the current implementation:

| Mockup block | Implementation (`source/web`) |
|--------------|------------------------------|
| **SEISMIC – Dashboard** | Page title / header |
| **REPLICAS – STATUS** | Replica chips / status (gateway polling) |
| **EVENTS – DATABASE** | Persisted events table (REST + SSE) |
| **RAM – LATEST CLASSIFICATIONS** | In-RAM classifications per replica (gateway) |

**Image file:** [`dashboard-mockup-lofi.png`](dashboard-mockup-lofi.png) — reference wireframe in the repo; you can replace it with your own exported PNG (same filename) if you want to version the original sketch.

Expected table columns: `time`, `sensor`, `class`, `freq`, `replica` — aligned with API and UI fields.
