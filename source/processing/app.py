"""
Replica di processing: ingestisce campioni dal broker, finestra scorrevole,
FFT, classificazione, persistenza idempotente su PostgreSQL (dedup_key),
stream di controllo SSE dal simulatore.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

LOG = logging.getLogger("processing")

SIMULATOR_BASE = os.environ.get("SIMULATOR_BASE_URL", "http://localhost:8080").rstrip("/")
REPLICA_ID = os.environ.get("REPLICA_ID", "1")
SAMPLING_RATE_HZ = float(os.environ.get("SAMPLING_RATE_HZ", "20"))
WINDOW_SIZE = int(os.environ.get("WINDOW_SIZE", "128"))
ENERGY_THRESHOLD = float(os.environ.get("ENERGY_THRESHOLD", "0"))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pool: asyncpg.Pool | None = None


class IngestBody(BaseModel):
    sensor_id: str
    timestamp: str
    value: float


@dataclass
class ReplicaState:
    # (valore, timestamp ISO del campione dal simulatore)
    windows: dict[str, deque[tuple[float, str]]] = field(default_factory=dict)
    recent_events: list[dict[str, Any]] = field(default_factory=list)


state = ReplicaState()


def make_dedup_key(
    sensor_id: str, classification: str, dom_freq: float, anchor_ts: str
) -> str:
    """Stessa finestra + stessi parametri → stessa chiave (repliche duplicate-safe)."""
    s = f"{sensor_id}|{classification}|{round(dom_freq, 4)}|{anchor_ts}"
    return hashlib.sha256(s.encode()).hexdigest()


def classify_dominant_freq_hz(freq_hz: float) -> str:
    if freq_hz < 0.5:
        return "below_band"
    if 0.5 <= freq_hz < 3.0:
        return "earthquake"
    if 3.0 <= freq_hz < 8.0:
        return "conventional_explosion"
    if freq_hz >= 8.0:
        return "nuclear_like"
    return "unknown"


def analyze_window(samples: list[float], fs: float) -> tuple[float | None, float]:
    x = np.asarray(samples, dtype=np.float64)
    n = len(x)
    if n < 8:
        return None, 0.0
    x = x - np.mean(x)
    spec = np.fft.rfft(x)
    power = (np.abs(spec) ** 2).astype(np.float64)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    if len(power) <= 1:
        return None, 0.0
    k = int(np.argmax(power[1:]) + 1)
    energy = float(np.sum(power[1:]))
    return float(freqs[k]), energy


def process_sample(sensor_id: str, value: float, sample_ts: str) -> dict[str, Any] | None:
    if sensor_id not in state.windows:
        state.windows[sensor_id] = deque(maxlen=WINDOW_SIZE)
    w = state.windows[sensor_id]
    w.append((value, sample_ts))
    if len(w) < WINDOW_SIZE:
        return None
    values = [t[0] for t in w]
    anchor_ts = w[-1][1]
    dom_freq, energy = analyze_window(values, SAMPLING_RATE_HZ)
    if dom_freq is None or energy < ENERGY_THRESHOLD:
        return None
    label = classify_dominant_freq_hz(dom_freq)
    if label == "below_band":
        return None
    dedup_key = make_dedup_key(sensor_id, label, dom_freq, anchor_ts)
    evt = {
        "dedup_key": dedup_key,
        "replica_id": REPLICA_ID,
        "sensor_id": sensor_id,
        "dominant_frequency_hz": round(dom_freq, 4),
        "energy": round(energy, 8),
        "classification": label,
        "detected_at": anchor_ts,
    }
    state.recent_events.append(evt)
    if len(state.recent_events) > 500:
        state.recent_events = state.recent_events[-250:]
    LOG.info("EVENT %s", evt)
    return evt


async def persist_event(p: asyncpg.Pool, evt: dict[str, Any]) -> None:
    """INSERT idempotente: seconda replica che calcola lo stesso evento viene ignorata."""
    sql = """
        INSERT INTO detected_events (
            dedup_key, sensor_id, classification, dominant_frequency_hz,
            energy, detected_at, replica_id
        )
        VALUES ($1, $2, $3, $4, $5, $6::timestamptz, $7)
        ON CONFLICT (dedup_key) DO NOTHING
    """
    await p.execute(
        sql,
        evt["dedup_key"],
        evt["sensor_id"],
        evt["classification"],
        evt["dominant_frequency_hz"],
        evt["energy"],
        evt["detected_at"],
        evt["replica_id"],
    )


async def sse_control_loop() -> None:
    url = f"{SIMULATOR_BASE}/api/control"
    LOG.info("REPLICA %s: connessione SSE %s", REPLICA_ID, url)
    while True:
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    event_name: str | None = None
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("event:"):
                            event_name = line[6:].strip()
                        elif line.startswith("data:"):
                            raw = line[5:].strip()
                            try:
                                data = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            if event_name == "command" and data.get("command") == "SHUTDOWN":
                                LOG.warning(
                                    "REPLICA %s: ricevuto SHUTDOWN — terminazione forzata",
                                    REPLICA_ID,
                                )
                                os._exit(0)
                            event_name = None
        except asyncio.CancelledError:
            raise
        except Exception as e:
            LOG.error("SSE errore (retry tra 2s): %s", e)
            await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    if DATABASE_URL:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        LOG.info("Pool PostgreSQL disponibile")
    else:
        LOG.warning("DATABASE_URL assente — nessuna persistenza su DB")
    task = asyncio.create_task(sse_control_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    if pool:
        await pool.close()
        pool = None


app = FastAPI(title=f"Processing replica {REPLICA_ID}", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "replica_id": REPLICA_ID,
        "window_size": WINDOW_SIZE,
        "sampling_rate_hz": SAMPLING_RATE_HZ,
        "sensors_tracked": len(state.windows),
        "persistence": bool(DATABASE_URL),
    }


@app.post("/internal/ingest")
async def ingest(body: IngestBody) -> dict[str, str]:
    try:
        evt = process_sample(body.sensor_id, body.value, body.timestamp)
        if evt and pool:
            await persist_event(pool, evt)
    except Exception as e:
        LOG.exception("ingest error: %s", e)
        raise HTTPException(status_code=500, detail="internal error") from e
    return {"status": "accepted"}


@app.get("/internal/recent-events")
def recent_events() -> list[dict[str, Any]]:
    return list(state.recent_events[-50:])


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
