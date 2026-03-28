-- Persistenza eventi classificati (idempotenza su dedup_key)
CREATE TABLE IF NOT EXISTS detected_events (
    id              BIGSERIAL PRIMARY KEY,
    dedup_key       CHAR(64) NOT NULL UNIQUE,
    sensor_id       TEXT NOT NULL,
    classification  TEXT NOT NULL,
    dominant_frequency_hz DOUBLE PRECISION NOT NULL,
    energy          DOUBLE PRECISION,
    detected_at     TIMESTAMPTZ NOT NULL,
    replica_id      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_detected_events_time ON detected_events (detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_detected_events_sensor ON detected_events (sensor_id);
