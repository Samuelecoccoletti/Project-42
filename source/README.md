# Running the stack (broker, processing, DB, gateway, **dashboard**)

From the **`source`** directory (where `docker-compose.yml` lives):

```bash
cd /path/to/Project-42/source
docker compose up -d --build
```

Wait until services are **Up** (first start may take 1–2 minutes).

## Dashboard (project front-end)

Open in the browser:

**http://localhost:3000**

This is not the simulator page (`8080`). If you only see the “Seismic Signal Simulator” Swagger UI, you are on the wrong port.

The dashboard calls APIs on **relative** `/api/...` paths (same host as the page). The **`web`** container (nginx) forwards `/api` to the **gateway** on the Docker network so the browser does not need `localhost:8090` (useful if Safari or a firewall blocks the second port). The gateway remains exposed on `8090` for direct tests (`curl`, manual Swagger).

## Check

```bash
docker compose ps
```

You should see the **`web`** service (`seismic-web`) with port `0.0.0.0:3000->80`.

If **`web` is missing** or **Exited**:

```bash
docker compose up -d web
docker compose logs web
```

## If something is stuck

```bash
docker compose down
docker compose up -d --build
```

Simulator Docker image: requires `seismic-signal-simulator:multiarch_v1` (see `scripts/load-simulator-oci.sh` in this `source` folder).

## SSE errors on the dashboard

If nginx forwards `/api` with `Connection: close` (typical `Upgrade`/`Connection` maps for WebSocket), **Safari** may close the SSE stream immediately. Current config does not set that header on the API proxy.

## Empty tables (DB and RAM)

You need the **broker** running (fan-out to replicas) and samples from the simulator. Processing only picks the FFT peak for frequencies **≥ 0.5 Hz** (`MIN_CLASSIFY_HZ`); otherwise most maxima sit in the first sub-0.5 Hz bin and no events appear.

## Replica error: «Name or service not known»

The simulator can send **`SHUTDOWN`** to one replica (SSE). That replica **exits** and the container stops responding: the gateway can no longer resolve `processing-1` or `processing-2`. Replicas in compose use **`restart: unless-stopped`** so they come back on their own. To disable automatic shutdowns: set `AUTO_SHUTDOWN_ENABLED=false` on the `simulator` service.
