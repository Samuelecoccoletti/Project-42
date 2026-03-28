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
