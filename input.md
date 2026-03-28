# Progetto — Laboratorio Advanced Programming 2025/2026

## Panoramica

Sistema distribuito per ingestione dati sismici dal **simulatore** (container fornito), **broker** con fan-out WebSocket → HTTP, **repliche di processing** con finestra scorrevole + FFT e classificazione per bande di frequenza, **PostgreSQL** con deduplicazione (`dedup_key`), **gateway** con failover e SSE, **dashboard** React.

Repository: `source/` (codice, Docker), `booklets/` (slide/diagrammi), questo file e `Student_doc.md`.

---

## User stories

*(Numerare e completare con il gruppo; sotto esempi tipici — adattare al vostro backlog.)*

| ID | Come … | Voglio … | Così che … | Priorità |
|----|---------|----------|------------|----------|
| US-01 | operatore | vedere lo stato delle repliche processing | capisco se il sistema è degradato | Must |
| US-02 | operatore | vedere gli eventi classificati persistiti | posso fare analisi storica | Must |
| US-03 | operatore | filtrare eventi per sensore | mi concentro su un’area | Should |
| US-04 | sistema | ignorare duplicati tra repliche sul DB | i dati restano coerenti | Must |
| US-05 | operatore | usare un’unica URL gateway | non devo conoscere le singole repliche | Should |
| US-06 | istruttore | iniettare eventi dal simulatore | posso testare classificazione | Could |
| US-07 | *(aggiungere)* | | | |

---

## Schema eventi standard (persistenza)

Allineato alla tabella `detected_events` e alle API gateway. Campi logici:

| Campo | Tipo | Note |
|-------|------|------|
| `dedup_key` | string (64 hex) | Unicità logica cross-replica |
| `sensor_id` | string | Es. `sensor-01` |
| `classification` | enum | `earthquake`, `conventional_explosion`, `nuclear_like`, … |
| `dominant_frequency_hz` | number | Da FFT |
| `energy` | number \| null | Energia spettrale (opzionale) |
| `detected_at` | ISO-8601 UTC | Ancora temporale del campione |
| `replica_id` | string | Replica che ha scritto per prima |

### Esempio JSON (risposta API)

```json
{
  "dedup_key": "a1b2…",
  "sensor_id": "sensor-11",
  "classification": "conventional_explosion",
  "dominant_frequency_hz": 6.719,
  "energy": 123.45,
  "detected_at": "2026-03-28T14:24:02.650816+00:00",
  "replica_id": "1",
  "created_at": "2026-03-28T14:24:03.120000+00:00"
}
```

---

## Modello di regole (classificazione)

Bande di frequenza dominante (dal testo d’esame, valori fittizi):

| Classe | Intervallo \(f\) (Hz) |
|--------|------------------------|
| Terremoto | \(0.5 \leq f < 3.0\) |
| Esplosione convenzionale | \(3.0 \leq f < 8.0\) |
| Nuclear-like | \(f \geq 8.0\) |
| Sotto banda / ignoto | \(f < 0.5\) o non classificato |

Regole di deduplicazione: stessa `dedup_key` = stesso `(sensor_id, classificazione, freq arrotondata, bucket temporale ~0,5 s sull’istante dell’ultimo campione)` per allineare le repliche (vedi `DEDUP_BUCKET_SEC` nel processing).

---

## Note di gruppo

- **Leader repo / matricola:** *(da compilare)*  
- **Componenti:** *(nomi)*
