"""
Gateway: persistence, replica status, failover routing to processing, SSE events.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://seismic:seismic@localhost:5432/seismic",
)

PROCESSING_URLS = [
    u.strip().rstrip("/")
    for u in os.environ.get(
        "PROCESSING_URLS",
        "http://processing-1:8000,http://processing-2:8000",
    ).split(",")
    if u.strip()
]

pool: asyncpg.Pool | None = None

# Round-robin across replicas; each request starts at the next URL, then failover on the rest.
_rr_lock = threading.Lock()
_rr_offset = 0


def _processing_urls_rotated() -> list[str]:
    """Return PROCESSING_URLS rotated so the start index advances (thread-safe)."""
    global _rr_offset
    if not PROCESSING_URLS:
        return []
    with _rr_lock:
        n = len(PROCESSING_URLS)
        start = _rr_offset % n
        _rr_offset += 1
    return PROCESSING_URLS[start:] + PROCESSING_URLS[:start]


def _event_row_to_dict(r: asyncpg.Record) -> dict[str, Any]:
    return {
        "dedup_key": r["dedup_key"],
        "sensor_id": r["sensor_id"],
        "classification": r["classification"],
        "dominant_frequency_hz": float(r["dominant_frequency_hz"]),
        "energy": float(r["energy"]) if r["energy"] is not None else None,
        "detected_at": r["detected_at"].isoformat(),
        "replica_id": r["replica_id"],
        "created_at": r["created_at"].isoformat(),
    }


async def _request_processing_failover(
    method: str,
    path: str,
    timeout: float = 5.0,
) -> tuple[Any, str]:
    """
    Try replicas in rotated order (round-robin): first 200 wins;
    others are tried on failover if error or status ≠ 200.
    Returns (JSON body, base_url of the replica that responded).
    """
    last_err: str | None = None
    order = _processing_urls_rotated()
    async with httpx.AsyncClient(timeout=timeout) as client:
        for base in order:
            url = f"{base}{path}"
            try:
                r = await client.request(method, url)
                if r.status_code == 200:
                    payload = r.json() if r.content else None
                    return payload, base
                last_err = f"{base} HTTP {r.status_code}"
            except Exception as e:
                last_err = f"{base}: {e}"
                continue
    raise HTTPException(
        status_code=503,
        detail="No processing replica available: " + (last_err or "unknown"),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    yield
    if pool:
        await pool.close()


app = FastAPI(title="Seismic Gateway", lifespan=lifespan)

_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins != ["*"] else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Processing-Replica"],
)


@app.get("/health")
async def health() -> dict[str, Any]:
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    replicas_ok = 0
    async with httpx.AsyncClient(timeout=2.0) as client:
        for base in PROCESSING_URLS:
            try:
                r = await client.get(f"{base}/health")
                if r.status_code == 200:
                    replicas_ok += 1
            except Exception:
                pass
    return {
        "status": "ok",
        "database": "reachable",
        "processing_replicas_healthy": replicas_ok,
        "processing_replicas_total": len(PROCESSING_URLS),
    }


@app.get("/api/replicas")
async def replicas_status() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=3.0) as client:
        for base in PROCESSING_URLS:
            try:
                r = await client.get(f"{base}/health")
                r.raise_for_status()
                out.append({"url": base, "ok": True, "health": r.json()})
            except Exception as e:
                out.append({"url": base, "ok": False, "error": str(e)})
    return out


@app.get("/api/processing/recent-events")
async def proxy_processing_recent_events() -> JSONResponse:
    """Forward to an online replica: per-replica local memory (debug / lab alignment)."""
    data, chosen_base = await _request_processing_failover("GET", "/internal/recent-events")
    if not isinstance(data, list):
        raise HTTPException(502, detail="Invalid processing response")
    return JSONResponse(
        content=data,
        headers={"X-Processing-Replica": chosen_base},
    )


@app.get("/api/events")
async def list_events(
    limit: int = Query(100, ge=1, le=500),
    sensor_id: str | None = None,
) -> list[dict[str, Any]]:
    assert pool is not None
    if sensor_id:
        rows = await pool.fetch(
            """
            SELECT dedup_key, sensor_id, classification, dominant_frequency_hz, energy,
                   detected_at, replica_id, created_at
            FROM detected_events
            WHERE sensor_id = $1
            ORDER BY detected_at DESC
            LIMIT $2
            """,
            sensor_id,
            limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT dedup_key, sensor_id, classification, dominant_frequency_hz, energy,
                   detected_at, replica_id, created_at
            FROM detected_events
            ORDER BY detected_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [_event_row_to_dict(r) for r in rows]


@app.get("/api/events/stream")
async def events_stream(
    sensor_id: str | None = Query(default=None, description="Filter to this sensor only"),
) -> StreamingResponse:
    """
    SSE: new DB events after connect (watermark on created_at).
    Sends a heartbeat each poll when there are no rows, to keep the connection alive.
    """
    assert pool is not None
    poll_s = float(os.environ.get("SSE_POLL_SECONDS", "2"))

    async def gen() -> AsyncIterator[bytes]:
        watermark = datetime.now(timezone.utc) - timedelta(seconds=30)
        try:
            while True:
                async with pool.acquire() as conn:
                    if sensor_id:
                        rows = await conn.fetch(
                            """
                            SELECT dedup_key, sensor_id, classification, dominant_frequency_hz, energy,
                                   detected_at, replica_id, created_at
                            FROM detected_events
                            WHERE sensor_id = $1 AND created_at > $2
                            ORDER BY created_at ASC
                            LIMIT 100
                            """,
                            sensor_id,
                            watermark,
                        )
                    else:
                        rows = await conn.fetch(
                            """
                            SELECT dedup_key, sensor_id, classification, dominant_frequency_hz, energy,
                                   detected_at, replica_id, created_at
                            FROM detected_events
                            WHERE created_at > $1
                            ORDER BY created_at ASC
                            LIMIT 100
                            """,
                            watermark,
                        )
                if rows:
                    ts_max = max(r["created_at"] for r in rows)
                    if ts_max > watermark:
                        watermark = ts_max
                    payload = json.dumps([_event_row_to_dict(r) for r in rows])
                    yield f"data: {payload}\n\n".encode()
                else:
                    yield b": hb\n\n"
                await asyncio.sleep(poll_s)
        except asyncio.CancelledError:
            raise

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8090"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
