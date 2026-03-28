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

### Cosa abbiamo implementato ora (probe)

Il servizio in `source/broker/` è una **versione minima**: scopre i sensori, apre **un** WebSocket e **stampa** alcuni campioni nei log.  
Serve a:

1. Verificare che rete e URL siano corretti (in locale o in Docker).
2. Fissare mentalmente il modello: **HTTP per discovery**, **WebSocket per stream**.
3. Preparare il passo successivo: stesso lettore, ma duplicazione del flusso verso più consumer (repliche).

## Passo 2 — Fan-out e repliche processing

### Teoria

- **Fan-out**: per ogni campione ricevuto dal WebSocket, il broker invia **la stessa copia** a **tutte** le URL in `PROCESSING_URLS` (HTTP `POST /internal/ingest`). È il broadcast richiesto dal testo.
- **Replica processing**: mantiene una **finestra scorrevole** di campioni **per sensore**; quando la finestra è piena applica **FFT**, trova la **frequenza dominante** e la mappa alle classi (terremoto / esplosione / nuclear-like) secondo le bande del PDF.
- **Control stream (SSE)**: ogni replica si connette a `GET /api/control` del simulatore. Se riceve `{"command":"SHUTDOWN"}`, **quella** replica deve terminare (il contratto ne notifica **una sola** alla volta).

### File

- `source/processing/` — API ingest + health + SSE + FFT.
- `source/broker/app.py` — fan-out verso `processing-1` e `processing-2`.

## Passo 3 — Persistenza e gateway

### Teoria

- Due repliche possono calcolare **lo stesso evento** a partire dagli stessi campioni. Serve un **dedup** deterministico:  
  `sha256(sensor_id | classificazione | freq arrotondata | timestamp dell’ultimo campione nella finestra)`.  
  Unico vincolo `UNIQUE(dedup_key)` + `INSERT ... ON CONFLICT DO NOTHING` → una sola riga in DB.
- **Gateway**: punto d’ingresso unico per **leggere** gli eventi (il lab richiede anche routing/health verso le repliche; qui espone già lista eventi e health sul DB).

### File

- `source/db/init.sql` — schema PostgreSQL.
- `source/gateway/` — API lettura eventi.
- `source/web/` — dashboard (build → nginx).

## Passo 4 — Dashboard

### Teoria

- **Aggiornamenti in tempo quasi reale**: il front-end chiama periodicamente (**polling** ~2,5 s) `GET /api/events` e `GET /api/replicas`. È tra le opzioni ammesse dal laboratorio (REST polling vs SSE/WebSocket lato dashboard).
- **CORS**: il browser carica la pagina da `localhost:3000` e le API da `localhost:8090` (origine diversa) → il gateway espone header CORS.
- **URL gateway**: in build Docker la variabile `VITE_GATEWAY_URL` è incollata nel bundle statico (`http://localhost:8090` quando apri il browser sulla macchina host).

## Passo 5 — Gateway: failover e SSE

### Teoria (allineamento al lab)

- **Routing verso repliche disponibili**: `GET /api/processing/recent-events` interroga le URL in `PROCESSING_URLS` in ordine; la **prima** che risponde 200 viene usata. Le altre sono saltate (replica “esclusa” fino al prossimo tentativo).
- **Health aggregato**: `GET /health` include quante repliche processing rispondono.
- **SSE**: `GET /api/events/stream` invia chunk `data:` con nuovi record da `detected_events` (watermark su `created_at`), più commenti heartbeat `: hb` per mantenere la connessione. Alternativa al solo polling REST per il requisito “real-time”.

### Dashboard

- **EventSource** sullo stream; merge per `dedup_key` per evitare duplicati.
- Seconda tabella: ultimi eventi **in RAM** dalla replica selezionata dal gateway (solo informativa; persistenza resta il DB).

## Note operative

- Simulatore: `http://localhost:8080` (vedi `source/docker-compose.yml` e `source/scripts/load-simulator-oci.sh`).
- Repliche: `http://localhost:8001` e `http://localhost:8002` (porte host mappate).
- Gateway: `http://localhost:8090/health`, `http://localhost:8090/api/events`, `http://localhost:8090/api/replicas`, `http://localhost:8090/api/processing/recent-events`, `http://localhost:8090/api/events/stream` (SSE).
- Dashboard: `http://localhost:3000` (dopo `docker compose up`).
- Debug eventi in memoria: `GET http://localhost:8001/internal/recent-events` (e analogo su 8002).
- Se il broker va in errore `keepalive ping timeout` su molti sensori: per default i **ping inviati dal client WebSocket sono disattivi** (`WS_PING_INTERVAL` / `WS_PING_TIMEOUT` vuoti); il traffico campioni mantiene la connessione. Riattiva i ping solo se serve, es. `WS_PING_INTERVAL=60`.
