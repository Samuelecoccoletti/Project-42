# Documentazione del sistema distribuito

## Architettura deployata

- **Simulatore** (8080): sensori WebSocket + SSE control.
- **Broker**: fan-out verso le repliche processing.
- **Processing ×2**: FFT/classificazione + scrittura su **PostgreSQL** con `dedup_key` unica.
- **PostgreSQL**: tabella `detected_events` (nessun DB embedded).
- **Gateway** (8090): REST eventi, **SSE** `/api/events/stream`, **`/api/processing/*` con failover** verso le repliche, CORS.
- **Web** (3000): dashboard React — SSE per nuovi eventi DB + REST iniziale; tab RAM replica via gateway.

## Servizi

Simulatore, broker, `processing-1`, `processing-2`, `db`, `gateway`, `web`.

## Passo 1 — Teoria: cos’è il broker e perché parte da qui

### Ruolo del simulatore (fornitore)

Il simulatore espone **N sensori virtuali**. Per ogni sensore:

- scopri l’id e il path WebSocket con **GET `/api/devices/`**;
- i campioni **non** arrivano via REST in polling: arrivano in **streaming** su  
  **WebSocket** `WS /api/device/{sensor_id}/ws`.

Ogni messaggio è un oggetto JSON con `timestamp` (UTC) e `value` (velocità di terra in mm/s).  
Il flusso è **continuo** (es. 20 Hz se `SAMPLING_RATE_HZ=20`): chi si connette riceve una sequenza infinita di campioni.

### Ruolo del broker (distribuzione, non intelligenza)

Il **broker** è il componente che **riceve** i dati grezzi dal simulatore e li **inoltra** alle **repliche di processing** (in un secondo momento: fan-out).  
Non deve fare FFT, classificazione o persistenza: solo **smistare** le misure.  
È l’unico punto che parla direttamente col simulatore per l’ingestione WebSocket; le repliche restano dietro al broker.

### Implementazione broker

Il servizio in `source/broker/` fa **discovery** (`GET /api/devices/`), apre **un WebSocket per sensore** (o un sottoinsieme se `ALL_SENSORS=false`) e per ogni campione esegue **fan-out** HTTP `POST /internal/ingest` verso tutte le URL in `PROCESSING_URLS`. Con `PROCESSING_URLS` vuoto resta la modalità **probe** (solo log). Variabili utili: `ALL_SENSORS`, `WS_PING_*`, `MAX_SAMPLES`.

## Passo 2 — Fan-out e repliche processing

### Teoria

- **Fan-out**: per ogni campione ricevuto dal WebSocket, il broker invia **la stessa copia** a **tutte** le URL in `PROCESSING_URLS` (HTTP `POST /internal/ingest`). È il broadcast richiesto dal testo.
- **Replica processing**: mantiene una **finestra scorrevole** di campioni **per sensore**; quando la finestra è piena applica **FFT**. Il picco si considera solo tra bin **≥ 0.5 Hz** (stessa soglia delle bande): altrimenti il massimo spesso cade sul primo bin (~\(f_s/N\), es. ~0.16 Hz a 20 Hz e 128 campioni) e ogni evento verrebbe scartato come «sotto banda».
- **Control stream (SSE)**: ogni replica si connette a `GET /api/control` del simulatore. Se riceve `{"command":"SHUTDOWN"}`, **quella** replica deve terminare (il contratto ne notifica **una sola** alla volta).

### File

- `source/processing/` — API ingest + health + SSE + FFT.
- `source/broker/app.py` — fan-out verso `processing-1` e `processing-2`.

## Passo 3 — Persistenza e gateway

### Teoria

- Due repliche possono calcolare **lo stesso evento** a partire dagli stessi campioni. Serve un **dedup** deterministico:  
  `sha256(sensor_id | classificazione | freq arrotondata | bucket temporale)`. Il bucket è `floor(t/0.5s)` sull’istante dell’ultimo campione (`DEDUP_BUCKET_SEC`), così piccoli sfasamenti tra repliche non creano due INSERT; il `detected_at` salvato resta il timestamp preciso della replica che vince la gara in scrittura.
  Unico vincolo `UNIQUE(dedup_key)` + `INSERT ... ON CONFLICT DO NOTHING` → una sola riga in DB.
- **Gateway**: punto d’ingresso unico per **leggere** gli eventi (il lab richiede anche routing/health verso le repliche; qui espone già lista eventi e health sul DB).

### File

- `source/db/init.sql` — schema PostgreSQL.
- `source/gateway/` — API lettura eventi.
- `source/web/` — dashboard (build → nginx).

## Passo 4 — Dashboard

### Teoria

- **Aggiornamenti in tempo quasi reale**: il front-end chiama periodicamente (**polling** ~2,5 s) `GET /api/events` e `GET /api/replicas`. È tra le opzioni ammesse dal laboratorio (REST polling vs SSE/WebSocket lato dashboard).
- **CORS**: in Docker la dashboard usa **stesso origine** (`3000` → nginx → gateway); in dev, `npm run dev` con proxy Vite. Se apri il bundle con `VITE_GATEWAY_URL=http://localhost:8090`, allora serve CORS sul gateway (già configurato con `CORS_ORIGINS`).
- **URL gateway**: in build Docker `VITE_GATEWAY_URL` è **vuota**; il front-end usa `/api/...` sulla stessa origine (`3000`) e **nginx** nel container `web` fa proxy verso il gateway. In sviluppo (`npm run dev`) Vite fa proxy di `/api` su `8090`. Per forzare l’URL assoluto del gateway, imposta `VITE_GATEWAY_URL` nella build.

## Passo 5 — Gateway: failover e SSE

### Teoria (allineamento al lab)

- **Routing verso repliche disponibili**: `GET /api/processing/recent-events` (e altre proxy verso processing) usa **round-robin** sulle URL in `PROCESSING_URLS`: ogni richiesta parte dalla replica “successiva”, così il carico di lettura si distribuisce. Se quella replica non risponde 200, il gateway **prova le altre** in failover fino a esaurimento (replica down = saltata per quel tentativo).
- **Health aggregato**: `GET /health` include quante repliche processing rispondono.
- **SSE**: `GET /api/events/stream` invia chunk `data:` con nuovi record da `detected_events` (watermark su `created_at`), più commenti heartbeat `: hb` per mantenere la connessione. Alternativa al solo polling REST per il requisito “real-time”. Se la dashboard mostra «stream in errore» (soprattutto Safari): non usare `Connection` vuoto sul proxy nginx verso il gateway; il front-end ignora `onerror` immediati e riconnette solo se lo stream resta chiuso.

### Dashboard

- **EventSource** sullo stream; merge per `dedup_key` per evitare duplicati.
- Seconda tabella: ultimi eventi **in RAM** dalla replica selezionata dal gateway (solo informativa; persistenza resta il DB).

## Note operative

- Simulatore: `http://localhost:8080` (vedi `source/docker-compose.yml` e `source/scripts/load-simulator-oci.sh`).
- Repliche: `http://localhost:8001` e `http://localhost:8002` (porte host mappate).
- Gateway: `http://localhost:8090/health`, `http://localhost:8090/api/events`, `http://localhost:8090/api/replicas`, `http://localhost:8090/api/processing/recent-events` (risposta con header `X-Processing-Replica`: URL della replica che ha servito), `http://localhost:8090/api/events/stream` (SSE).
- Dashboard: `http://localhost:3000` (dopo `docker compose up`).
- Debug eventi in memoria: `GET http://localhost:8001/internal/recent-events` (e analogo su 8002).
- Se il broker va in errore `keepalive ping timeout` su molti sensori: per default i **ping inviati dal client WebSocket sono disattivi** (`WS_PING_INTERVAL` / `WS_PING_TIMEOUT` vuoti); il traffico campioni mantiene la connessione. Riattiva i ping solo se serve, es. `WS_PING_INTERVAL=60`.

### RAM popolata ma PostgreSQL vuoto

La RAM è locale alla replica; il DB richiede `DATABASE_URL` e insert riusciti. Se vedi eventi nella tab RAM ma zero righe in `detected_events`: controlla `GET http://localhost:8001/health` → `persistence: true`; nei log della replica, messaggi `DATABASE_URL assente` o `ingest error`. Avvia lo stack da `source/` con `docker compose` così le variabili d’ambiente sulle repliche sono coerenti.

Diagramma ad alto livello: `booklets/architecture.md` (Mermaid).

### «Name or service not known» su `processing-2` (o 1)

Il simulatore può mandare **`SHUTDOWN`** su SSE: la replica interessata termina (`os._exit`). Il container resta **spento** finché non viene riavviato; gli altri servizi non risolvono più il nome Docker e in dashboard compare `[Errno -2] Name or service not known`. In `docker-compose.yml` le repliche hanno **`restart: unless-stopped`** così tornano su dopo un fault injection. Per prove senza spegnimenti: nel simulatore imposta `AUTO_SHUTDOWN_ENABLED=false` (vedi `docker-compose.yml`).
