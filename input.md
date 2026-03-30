# Project42

## Repository layout

Distributed stack: `source/` (code, Docker), `booklets/` (slides, diagrams), this file and `Student_doc.md`.

---

# SYSTEM DESCRIPTION

Project42 is a strategic surveillance platform for real-time monitoring of global seismic signals. Its purpose is to distinguish natural events from man-made threats, such as conventional or nuclear-like activity.

The system uses a **distributed architecture**: a **neutral broker** receives data from sensors and forwards it to **replicated processing nodes**. Those nodes analyse signals with **FFT** (Fast Fourier Transform). The design targets **resilience** when compute nodes fail (e.g. simulated shutdown), so monitoring can continue while replicas restart or degrade gracefully behind the gateway.

---

# USER STORIES 

| ID | Role (Persona) | Requirement (I want...) | Motivation (So that...) | Priority |
| :--- | :--- | :--- | :--- | :--- |
| **US-01** | Broker (Ingestion) | Open WebSocket connections to each sensor stream | Real-time samples are received for downstream processing | **Must** |
| **US-02** | Neutral Broker | Forward incoming samples to multiple processing nodes | Intelligence is not analysed in the neutral routing tier | **Must** |
| **US-03** | Data Analyst | Compute the dominant frequency with FFT | The nature of the vibration can be assessed | **Must** |
| **US-04** | Military Commander | Classify signals 0.5 ≤ f < 3.0 Hz as earthquake-like | Natural seismic activity can be separated from threats | **Must** |
| **US-05** | Defence Operator | Classify signals 3.0 ≤ f < 8.0 Hz as conventional explosion | Nearby units can be alerted | **Must** |
| **US-06** | High Command | Immediate nuclear-like alert for frequency ≥ 8.0 Hz | Emergency defensive protocols can be considered | **Must** |
| **US-07** | IT Administrator | Replicate processing service across two containers | System keeps operating if one node is lost or shut down | **Must** |
| **US-08** | Database Steward | Idempotent persistence | Duplicate detections from different replicas are stored only once | **Must** |
| **US-09** | Command-centre Op. | Real-time dashboard showing recent detected events | Recent events and their classification are visible | **Must** |
| **US-10** | Strategic Researcher | Historical log of persisted threats | Patterns in activity can be reviewed | **Must** |
| **US-11** | Security Officer | Replicas to react to a SHUTDOWN command over SSE | Simulated node failure matches the lab contract | **Must** |
| **US-12** | Technical User | See health status of distributed nodes on dashboard | Distributed system status is monitored | **Must** |
| **US-13** | Field Analyst | Show the sensor ID for every alert | The source channel of the detection is explicit | **Should** |
| **US-14** | Deployment Engineer | Start the whole stack with a single `docker compose up` | Repeatable field-style deployment is ensured | **Must** |
| **US-15** | Developer | Sliding window of samples per sensor | Frequency analysis is stable | **Must** ||

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
