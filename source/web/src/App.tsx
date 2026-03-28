import { useCallback, useEffect, useState } from "react";

const GW =
  import.meta.env.VITE_GATEWAY_URL?.replace(/\/$/, "") ||
  "http://localhost:8090";

export type EventRow = {
  dedup_key: string;
  sensor_id: string;
  classification: string;
  dominant_frequency_hz: number;
  energy: number | null;
  detected_at: string;
  replica_id: string;
  created_at: string;
};

export type ReplicaRow = {
  url: string;
  ok: boolean;
  health?: Record<string, unknown>;
  error?: string;
};

function mergeEvents(prev: EventRow[], batch: EventRow[]): EventRow[] {
  const map = new Map(prev.map((e) => [e.dedup_key, e]));
  for (const e of batch) map.set(e.dedup_key, e);
  return Array.from(map.values())
    .sort((a, b) => b.detected_at.localeCompare(a.detected_at))
    .slice(0, 200);
}

export function App() {
  const [events, setEvents] = useState<EventRow[]>([]);
  const [replicas, setReplicas] = useState<ReplicaRow[]>([]);
  const [sensorFilter, setSensorFilter] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [streamOk, setStreamOk] = useState<boolean | null>(null);
  const [replicaEvents, setReplicaEvents] = useState<EventRow[]>([]);

  const loadReplicas = useCallback(async () => {
    try {
      const rRes = await fetch(`${GW}/api/replicas`);
      if (!rRes.ok) throw new Error(`repliche HTTP ${rRes.status}`);
      setReplicas(await rRes.json());
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  const loadEventsOnce = useCallback(async () => {
    try {
      const q = new URLSearchParams();
      q.set("limit", "100");
      if (sensorFilter.trim()) q.set("sensor_id", sensorFilter.trim());
      const eRes = await fetch(`${GW}/api/events?${q}`);
      if (!eRes.ok) throw new Error(`eventi HTTP ${eRes.status}`);
      setEvents(await eRes.json());
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }, [sensorFilter]);

  const loadReplicaMemory = useCallback(async () => {
    try {
      const r = await fetch(`${GW}/api/processing/recent-events`);
      if (!r.ok) {
        setReplicaEvents([]);
        return;
      }
      const data = await r.json();
      setReplicaEvents(Array.isArray(data) ? data : []);
    } catch {
      setReplicaEvents([]);
    }
  }, []);

  useEffect(() => {
    void loadEventsOnce();
  }, [loadEventsOnce]);

  useEffect(() => {
    void loadReplicas();
    const id = setInterval(() => void loadReplicas(), 4000);
    return () => clearInterval(id);
  }, [loadReplicas]);

  useEffect(() => {
    void loadReplicaMemory();
    const id = setInterval(() => void loadReplicaMemory(), 5000);
    return () => clearInterval(id);
  }, [loadReplicaMemory]);

  useEffect(() => {
    const q = new URLSearchParams();
    if (sensorFilter.trim()) q.set("sensor_id", sensorFilter.trim());
    const url = `${GW}/api/events/stream${q.toString() ? `?${q}` : ""}`;
    const es = new EventSource(url);
    setStreamOk(true);
    es.onmessage = (ev) => {
      try {
        const batch = JSON.parse(ev.data) as EventRow[];
        if (Array.isArray(batch) && batch.length > 0) {
          setEvents((prev) => mergeEvents(prev, batch));
        }
      } catch {
        /* ignore */
      }
    };
    es.onerror = () => {
      setStreamOk(false);
    };
    return () => {
      es.close();
    };
  }, [sensorFilter]);

  return (
    <div className="app">
      <header>
        <h1>Seismic — dashboard</h1>
        <p className="muted">
          Eventi PostgreSQL: <strong>SSE</strong>{" "}
          {streamOk === false ? (
            <span className="error">(stream in errore — usa &quot;Aggiorna&quot;)</span>
          ) : (
            <span>+ caricamento iniziale</span>
          )}
          . Gateway: <a href={GW}>{GW}</a>
        </p>
      </header>

      <section className="panel">
        <h2>Repliche processing</h2>
        <div className="replicas">
          {replicas.map((r) => (
            <div key={r.url} className={`chip ${r.ok ? "ok" : "bad"}`}>
              {r.url.replace(/^https?:\/\//, "")} —{" "}
              {r.ok ? "online" : r.error ?? "offline"}
            </div>
          ))}
          {replicas.length === 0 && (
            <span className="muted">Nessun dato repliche.</span>
          )}
        </div>
        <p className="muted small">
          Il gateway instrada <code>/api/processing/recent-events</code> verso la
          prima valida (failover).
        </p>
      </section>

      <section className="panel">
        <h2>Eventi persistiti (PostgreSQL)</h2>
        <div className="row">
          <label>
            Filtra sensore{" "}
            <input
              value={sensorFilter}
              onChange={(e) => setSensorFilter(e.target.value)}
              placeholder="es. sensor-01"
            />
          </label>
          <button type="button" onClick={() => void loadEventsOnce()}>
            Aggiorna ora (REST)
          </button>
        </div>
        {err && <p className="error">{err}</p>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Tempo (UTC)</th>
                <th>Sensore</th>
                <th>Classe</th>
                <th>Freq Hz</th>
                <th>Replica</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev) => (
                <tr key={ev.dedup_key}>
                  <td>{ev.detected_at}</td>
                  <td>{ev.sensor_id}</td>
                  <td>{ev.classification}</td>
                  <td>{ev.dominant_frequency_hz.toFixed(4)}</td>
                  <td>{ev.replica_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {events.length === 0 && !err && (
            <p className="muted">Nessun evento in tabella (o DB ancora vuoto).</p>
          )}
        </div>
      </section>

      <section className="panel">
        <h2>Ultime classificazioni in RAM (replica via gateway)</h2>
        <p className="muted small">
          Campione dalla prima replica disponibile; non sostituisce il DB.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Tempo</th>
                <th>Sensore</th>
                <th>Classe</th>
                <th>Freq</th>
                <th>R</th>
              </tr>
            </thead>
            <tbody>
              {replicaEvents.slice(-12).map((ev) => (
                <tr key={`${ev.dedup_key}-ram`}>
                  <td>{ev.detected_at}</td>
                  <td>{ev.sensor_id}</td>
                  <td>{ev.classification}</td>
                  <td>{ev.dominant_frequency_hz?.toFixed?.(3) ?? ev.dominant_frequency_hz}</td>
                  <td>{ev.replica_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {replicaEvents.length === 0 && (
            <p className="muted">Nessun dato o repliche non raggiungibili.</p>
          )}
        </div>
      </section>
    </div>
  );
}
