"""
Replica di processing: ingestisce campioni dal broker, finestra scorrevole,
FFT, classificazione per bande di frequenza, stream di controllo SSE dal simulatore.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

LOG = logging.getLogger("processing")

SIMULATOR_BASE = os.environ.get("SIMULATOR_BASE_URL", "http://localhost:8080").rstrip("/")
REPLICA_ID = os.environ.get("REPLICA_ID", "1")
SAMPLING_RATE_HZ = float(os.environ.get("SAMPLING_RATE_HZ", "20"))
WINDOW_SIZE = int(os.environ.get("WINDOW_SIZE", "128"))
# Soglia minima energia (somma |FFT|^2 normalizzata) per considerare un picco valido
ENERGY_THRESHOLD = float(os.environ.get("ENERGY_THRESHOLD", "0"))


class IngestBody(BaseModel):
    sensor_id: str
    timestamp: str
    value: float


@dataclass
class ReplicaState:
    windows: dict[str, deque[float]] = field(default_factory=dict)
    # Ultimi eventi rilevati (per debug / futura API dashboard)
    recent_events: list[dict[str, Any]] = field(default_factory=list)


state = ReplicaState()


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
    """Restituisce (frequenza dominante Hz, energia totale spettrale)."""
    x = np.asarray(samples, dtype=np.float64)
    n = len(x)
    if n < 8:
        return None, 0.0
    x = x - np.mean(x)
    spec = np.fft.rfft(x)
    power = (np.abs(spec) ** 2).astype(np.float64)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    # ignora DC
    if len(power) <= 1:
        return None, 0.0
    k = int(np.argmax(power[1:]) + 1)
    energy = float(np.sum(power[1:]))
    return float(freqs[k]), energy


def process_sample(sensor_id: str, value: float) -> None:
    if sensor_id not in state.windows:
        state.windows[sensor_id] = deque(maxlen=WINDOW_SIZE)
    w = state.windows[sensor_id]
    w.append(value)
    if len(w) < WINDOW_SIZE:
        return
    dom_freq, energy = analyze_window(list(w), SAMPLING_RATE_HZ)
    if dom_freq is None or energy < ENERGY_THRESHOLD:
        return
    label = classify_dominant_freq_hz(dom_freq)
    if label == "below_band":
        return
    evt = {
        "replica_id": REPLICA_ID,
        "sensor_id": sensor_id,
        "dominant_frequency_hz": round(dom_freq, 4),
        "energy": round(energy, 8),
        "classification": label,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
    state.recent_events.append(evt)
    if len(state.recent_events) > 500:
        state.recent_events = state.recent_events[-250:]
    LOG.info("EVENT %s", evt)


async def sse_control_loop() -> None:
    """Ascolta /api/control; su SHUTDOWN termina il processo (replica simulata)."""
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
    task = asyncio.create_task(sse_control_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title=f"Processing replica {REPLICA_ID}", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "replica_id": REPLICA_ID,
        "window_size": WINDOW_SIZE,
        "sampling_rate_hz": SAMPLING_RATE_HZ,
        "sensors_tracked": len(state.windows),
    }


@app.post("/internal/ingest")
async def ingest(body: IngestBody) -> dict[str, str]:
    try:
        process_sample(body.sensor_id, body.value)
    except Exception as e:
        LOG.exception("ingest error: %s", e)
        raise HTTPException(status_code=500, detail="internal error") from e
    return {"status": "accepted"}


@app.get("/internal/recent-events")
def recent_events() -> list[dict[str, Any]]:
    """Endpoint di debug per vedere cosa ha classificato questa replica."""
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
