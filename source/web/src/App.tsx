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

export function App() {
  const [events, setEvents] = useState<EventRow[]>([]);
  const [replicas, setReplicas] = useState<ReplicaRow[]>([]);
  const [sensorFilter, setSensorFilter] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const q = new URLSearchParams();
      q.set("limit", "100");
      if (sensorFilter.trim()) q.set("sensor_id", sensorFilter.trim());
      const [eRes, rRes] = await Promise.all([
        fetch(`${GW}/api/events?${q}`),
        fetch(`${GW}/api/replicas`),
      ]);
      if (!eRes.ok) throw new Error(`eventi HTTP ${eRes.status}`);
      if (!rRes.ok) throw new Error(`repliche HTTP ${rRes.status}`);
      setEvents(await eRes.json());
      setReplicas(await rRes.json());
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }, [sensorFilter]);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 2500);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="app">
      <header>
        <h1>Seismic — dashboard</h1>
        <p className="muted">
          Aggiornamento automatico ogni ~2,5 s. API gateway:{" "}
          <a href={GW}>{GW}</a>
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
      </section>

      <section className="panel">
        <h2>Eventi rilevati (PostgreSQL)</h2>
        <div className="row">
          <label>
            Filtra sensore{" "}
            <input
              value={sensorFilter}
              onChange={(e) => setSensorFilter(e.target.value)}
              placeholder="es. sensor-01"
            />
          </label>
          <button type="button" onClick={() => void load()}>
            Aggiorna ora
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
    </div>
  );
}
