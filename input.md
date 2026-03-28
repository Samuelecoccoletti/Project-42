# Project42

## Repository layout

Distributed stack: `source/` (code, Docker), `booklets/` (slides, diagrams), this file and `Student_doc.md`.

---

# SYSTEM DESCRIPTION

Project42 is a strategic surveillance platform for real-time monitoring of global seismic signals. Its purpose is to distinguish natural events from man-made threats, such as conventional or nuclear-like activity.

The system uses a **distributed architecture**: a **neutral broker** receives data from sensors and forwards it to **replicated processing nodes**. Those nodes analyse signals with **FFT** (Fast Fourier Transform). The design targets **resilience** when compute nodes fail (e.g. simulated shutdown), so monitoring can continue while replicas restart or degrade gracefully behind the gateway.

---

# USER STORIES

Each item starts with its id on the same line as the story text. Priorities are summarised in the table after the list.

**US-01** — As the **broker (ingestion component)**, I want to open WebSocket connections to each sensor stream exposed by the simulator so that real-time ground-vibration samples are received continuously for downstream processing.

**US-02** — As a **neutral broker**, I want to forward incoming samples to multiple processing nodes so that intelligence is not analysed in the neutral routing tier.

**US-03** — As a **data analyst**, I want the system to compute the dominant frequency with FFT so that the nature of the vibration can be assessed.

**US-04** — As a **military commander**, I want signals with dominant frequency f such that 0.5 ≤ f < 3.0 Hz classified as earthquake-like so that natural seismic activity can be separated from threats.

**US-05** — As a **defence operator**, I want signals with dominant frequency f such that 3.0 ≤ f < 8.0 Hz classified as conventional explosion so that nearby units can be alerted.

**US-06** — As **high command**, I want an immediate nuclear-like alert for dominant frequency ≥ 8.0 Hz so that emergency defensive protocols can be considered.

**US-07** — As an **IT administrator**, I want the processing service replicated across two containers so that the system keeps operating if one node is lost or shut down.

**US-08** — As a **database steward**, I want idempotent persistence so that duplicate detections from different replicas are stored only once.

**US-09** — As a **command-centre operator**, I want a real-time dashboard showing recent detected events and their classification.

**US-10** — As a **strategic researcher**, I want a historical log of persisted threats so that patterns in activity can be reviewed.

**US-11** — As a **security officer**, I want replicas to react to a SHUTDOWN command over SSE so that simulated node failure matches the lab fault-injection contract.

**US-12** — As a **technical user**, I want to see health status of distributed processing nodes from the dashboard.

**US-13** — As a **field analyst**, I want every alert to show the sensor ID so that the source channel of the detection is explicit (mapping to geography is a separate operational concern).

**US-14** — As a **deployment engineer**, I want to start the whole stack with a single `docker compose up` for repeatable field-style deployment.

**US-15** — As a **developer**, I want a sliding window of samples per sensor so that frequency analysis is stable.

| ID | Priority |
|----|----------|
| US-01 | Must |
| US-02 | Must |
| US-03 | Must |
| US-04 | Must |
| US-05 | Must |
| US-06 | Must |
| US-07 | Must |
| US-08 | Must |
| US-09 | Must |
| US-10 | Must |
| US-11 | Must |
| US-12 | Must |
| US-13 | Should |
| US-14 | Must |
| US-15 | Must |

Priority: Must = baseline required by the lab brief. Should on US-13 marks analyst-facing emphasis on sensor identity (no built-in geolocation in scope).

---

## Standard persisted event schema

Aligned with table `detected_events` and gateway APIs.

| Field | Type | Notes |
|-------|------|-------|
| `dedup_key` | string (64 hex) | Logical uniqueness across replicas |
| `sensor_id` | string | e.g. `sensor-01` |
| `classification` | string | `earthquake`, `conventional_explosion`, `nuclear_like`, … |
| `dominant_frequency_hz` | number | From FFT |
| `energy` | number \| null | Spectral energy (optional) |
| `detected_at` | ISO-8601 UTC | Anchor timestamp of the sample |
| `replica_id` | string | Replica that won the insert race |
| `created_at` | ISO-8601 UTC | Row insert time (set by the database) |

### Example JSON (API response)

```json
{
  "dedup_key": "a1b2c3…",
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

## Classification rule model

Dominant-frequency bands (exam brief; fictional thresholds):

| Class | Interval \(f\) (Hz) |
|-------|---------------------|
| Earthquake | \(0.5 \leq f < 3.0\) |
| Conventional explosion | \(3.0 \leq f < 8.0\) |
| Nuclear-like | \(f \geq 8.0\) |
| Below band / ignored | \(f < 0.5\) or unclassified |

Deduplication: same `dedup_key` corresponds to the same logical event across replicas (sensor, class, rounded frequency, time bucket on the last sample; see `DEDUP_BUCKET_SEC` in processing).

---

## Group metadata

- **Repository lead / student ID:** 2092748  
- **Team members:** Project42 — Samuele Coccoletti and Chiara Andreoli
