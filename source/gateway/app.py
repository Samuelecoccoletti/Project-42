"""
Gateway: ingresso unico verso la persistenza (lista eventi, health).
Il front-end consumerà questi endpoint; in seguito si aggiunge routing verso le repliche.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from fastapi import FastAPI, Query

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://seismic:seismic@localhost:5432/seismic",
)

pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    yield
    if pool:
        await pool.close()


app = FastAPI(title="Seismic Gateway", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return {"status": "ok", "database": "reachable"}


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
    out = []
    for r in rows:
        out.append(
            {
                "dedup_key": r["dedup_key"],
                "sensor_id": r["sensor_id"],
                "classification": r["classification"],
                "dominant_frequency_hz": float(r["dominant_frequency_hz"]),
                "energy": float(r["energy"]) if r["energy"] is not None else None,
                "detected_at": r["detected_at"].isoformat(),
                "replica_id": r["replica_id"],
                "created_at": r["created_at"].isoformat(),
            }
        )
    return out


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8090"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
