"""
Broker: discovery + WebSocket dal simulatore, fan-out HTTP verso le repliche processing.

Se PROCESSING_URLS è vuoto, si comporta come probe (solo log).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

LOG = logging.getLogger("broker")

# Keepalive: con molti sensori + fan-out, il client può non rispondere ai ping in tempo.
WS_PING_INTERVAL = int(os.environ.get("WS_PING_INTERVAL", "30"))
WS_PING_TIMEOUT = int(os.environ.get("WS_PING_TIMEOUT", "120"))

SIMULATOR_BASE = os.environ.get("SIMULATOR_BASE_URL", "http://localhost:8080").rstrip("/")
MAX_SAMPLES = int(os.environ.get("MAX_SAMPLES", "0"))
SENSOR_ID = os.environ.get("SENSOR_ID", "").strip()
ALL_SENSORS = os.environ.get("ALL_SENSORS", "true").lower() in ("1", "true", "yes", "on")

# Es: http://processing-1:8000,http://processing-2:8000
PROCESSING_URLS = [
    u.strip().rstrip("/")
    for u in os.environ.get("PROCESSING_URLS", "").split(",")
    if u.strip()
]


def http_to_ws_base(http_base: str) -> str:
    if http_base.startswith("https://"):
        return "wss://" + http_base[len("https://") :]
    if http_base.startswith("http://"):
        return "ws://" + http_base[len("http://") :]
    raise ValueError(f"URL non supportato: {http_base}")


async def fetch_sensors(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    r = await client.get(f"{SIMULATOR_BASE}/api/devices/")
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise TypeError("Risposta /api/devices/ attesa come lista")
    return data


async def fan_out(
    http_client: httpx.AsyncClient,
    sensor_id: str,
    payload: dict[str, Any],
) -> None:
    """Invia lo stesso campione a tutte le repliche (broadcast)."""
    body = {"sensor_id": sensor_id, **payload}
    if not PROCESSING_URLS:
        LOG.debug("[%s] %s", sensor_id, body)
        return

    async def post_one(base: str) -> None:
        url = f"{base}/internal/ingest"
        try:
            r = await http_client.post(url, json=body)
            r.raise_for_status()
        except Exception as e:
            LOG.warning("ingest fallito verso %s: %s", base, e)

    await asyncio.gather(*[post_one(base) for base in PROCESSING_URLS])


async def read_sensor_stream(
    http_client: httpx.AsyncClient,
    ws_path: str,
    sensor_id: str,
    label: str,
) -> None:
    ws_base = http_to_ws_base(SIMULATOR_BASE)
    uri = f"{ws_base}{ws_path}" if ws_path.startswith("/") else f"{ws_base}/{ws_path}"
    LOG.info("WS %s (%s)", uri, label)
    n_total = 0
    backoff = 1
    connect_kw = {
        "ping_interval": WS_PING_INTERVAL,
        "ping_timeout": WS_PING_TIMEOUT,
        "close_timeout": 10,
    }
    while True:
        try:
            async with websockets.connect(uri, **connect_kw) as ws:
                backoff = 1
                while True:
                    raw = await ws.recv()
                    payload = json.loads(raw)
                    n_total += 1
                    if PROCESSING_URLS:
                        await fan_out(http_client, sensor_id, payload)
                    else:
                        LOG.info("[%s] %s", label, payload)
                    if MAX_SAMPLES and n_total >= MAX_SAMPLES:
                        LOG.info("MAX_SAMPLES=%s raggiunto per %s", MAX_SAMPLES, label)
                        return
        except ConnectionClosed as e:
            LOG.warning(
                "WS %s chiuso (%s), riconnessione tra %ss...", label, e, backoff
            )
        except OSError as e:
            LOG.warning("%s errore rete (%s), retry tra %ss...", label, e, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


async def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not PROCESSING_URLS:
        LOG.warning(
            "PROCESSING_URLS vuoto — modalità probe (solo log). "
            "Imposta gli URL delle repliche per il fan-out."
        )
    else:
        LOG.info("Fan-out verso %s", PROCESSING_URLS)

    async with httpx.AsyncClient(timeout=30.0) as discover_client:
        sensors = await fetch_sensors(discover_client)

    if SENSOR_ID:
        sensors = [s for s in sensors if s.get("id") == SENSOR_ID]
        if not sensors:
            LOG.error("Nessun sensore con id=%r", SENSOR_ID)
            sys.exit(1)
    elif not sensors:
        LOG.error("Nessun sensore restituito dal simulatore")
        sys.exit(1)
    elif not ALL_SENSORS:
        sensors = sensors[:1]

    tasks = []
    for s in sensors:
        sid = s.get("id", "?")
        path = s.get("websocket_url")
        if not path:
            LOG.error("Sensore %s senza websocket_url", sid)
            continue
        name = s.get("name", sid)
        tasks.append((path, sid, f"{sid} {name}"))

    if not tasks:
        sys.exit(1)

    async with httpx.AsyncClient(timeout=10.0) as http_client:
        await asyncio.gather(
            *[read_sensor_stream(http_client, p, sid, lbl) for p, sid, lbl in tasks]
        )


if __name__ == "__main__":
    asyncio.run(main())
