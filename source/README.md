# Avvio stack (broker, processing, DB, gateway, **dashboard**)

Dalla cartella **`source`** (dove c’è `docker-compose.yml`):

```bash
cd /path/to/Project-42/source
docker compose up -d --build
```

Attendi che i servizi siano **Up** (può richiedere 1–2 minuti al primo avvio).

## Dashboard (front-end del progetto)

Apri nel browser:

**http://localhost:3000**

Non è la pagina del simulatore (`8080`). Se vedi solo Swagger “Seismic Signal Simulator”, sei sulla porta sbagliata.

La dashboard chiama le API su **percorsi relativi** `/api/...` (stesso host della pagina). Il container **`web`** (nginx) inoltra `/api` al **gateway** sulla rete Docker: così il browser non richiede `localhost:8090` (utile se Safari o firewall bloccano il secondo porto). Il gateway resta comunque esposto su `8090` per test diretti (`curl`, Swagger manuale).

## Verifica

```bash
docker compose ps
```

Deve comparire il servizio **`web`** (container `seismic-web`) con porta `0.0.0.0:3000->80`.

Se **`web` manca** o è `Exited`:

```bash
docker compose up -d web
docker compose logs web
```

## Se qualcosa è incastrato

```bash
docker compose down
docker compose up -d --build
```

Simulatore Docker: richiede l’immagine `seismic-signal-simulator:multiarch_v1` (vedi `scripts/load-simulator-oci.sh` nella stessa cartella `source`).

## SSE in errore sulla dashboard

Se nginx inoltra `/api` con `Connection: close` (tipico di map `Upgrade`/`Connection` per WebSocket), **Safari** può chiudere subito lo stream SSE. La config attuale non imposta quel header sul proxy API.

## Tabelle vuote (DB e RAM)

Serve **broker** in esecuzione (fan-out verso le repliche) e campioni dal simulatore. Il processing calcola il picco FFT solo su frequenze **≥ 0.5 Hz** (`MIN_CLASSIFY_HZ`), altrimenti quasi tutti i massimi cadevano nel primo bin sub-0.5 Hz e non compariva nessun evento.

## Replica in errore: «Name or service not known»

Il simulatore può inviare **`SHUTDOWN`** a una replica (SSE). Quella replica **esce** e il container smette di rispondere: il gateway non risolve più `processing-1` o `processing-2`. Le repliche nel compose hanno **`restart: unless-stopped`** per ripartire da sole. Per disattivare gli shutdown automatici: `AUTO_SHUTDOWN_ENABLED=false` sul servizio `simulator`.
