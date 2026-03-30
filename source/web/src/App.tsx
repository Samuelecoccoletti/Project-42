import { useCallback, useEffect, useState } from "react";

const rawGw = import.meta.env.VITE_GATEWAY_URL as string | undefined;
/** Empty string = relative `/api/...` URLs (Vite proxy in dev, nginx in `web` container). */
const GW =
  rawGw !== undefined && String(rawGw).trim() !== ""
    ? String(rawGw).replace(/\/$/, "")
    : "";

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
  const [ramSourceUrl, setRamSourceUrl] = useState<string | null>(null);

  const loadReplicas = useCallback(async () => {
    try {
      const rRes = await fetch(`${GW}/api/replicas`);
      if (!rRes.ok) throw new Error(`replicas HTTP ${rRes.status}`);
      setReplicas(await rRes.json());
    } catch (e) {
      const hint = GW || (typeof window !== "undefined" ? window.location.origin : "");
      setErr(
        `API unreachable (${hint}). Start the stack from source/ and reload: ${String(e)}`,
      );
    }
  }, []);

  const loadEventsOnce = useCallback(async () => {
    try {
      const q = new URLSearchParams();
      q.set("limit", "100");
      if (sensorFilter.trim()) q.set("sensor_id", sensorFilter.trim());
      const eRes = await fetch(`${GW}/api/events?${q}`);
      if (!eRes.ok) throw new Error(`events HTTP ${eRes.status}`);
      setEvents(await eRes.json());
      setErr(null);
    } catch (e) {
      const hint = GW || (typeof window !== "undefined" ? window.location.origin : "");
      setErr(`API unreachable (${hint}): ${String(e)}`);
    }
  }, [sensorFilter]);

  const loadReplicaMemory = useCallback(async () => {
    try {
      const r = await fetch(`${GW}/api/processing/recent-events`);
      if (!r.ok) {
        setReplicaEvents([]);
        setRamSourceUrl(null);
        return;
      }
      const src = r.headers.get("X-Processing-Replica");
      setRamSourceUrl(src);
      const data = await r.json();
      setReplicaEvents(Array.isArray(data) ? data : []);
    } catch {
      setReplicaEvents([]);
      setRamSourceUrl(null);
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
    let cancelled = false;
    let es: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let errDebounce: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      if (cancelled) return;
      const q = new URLSearchParams();
      if (sensorFilter.trim()) q.set("sensor_id", sensorFilter.trim());
      const url = `${GW}/api/events/stream${q.toString() ? `?${q}` : ""}`;
      es?.close();
      const inst = new EventSource(url);
      es = inst;
      inst.onopen = () => {
        if (errDebounce !== undefined) {
          window.clearTimeout(errDebounce);
          errDebounce = undefined;
        }
        if (!cancelled) setStreamOk(true);
      };
      inst.onmessage = (ev) => {
        try {
          const batch = JSON.parse(ev.data) as EventRow[];
          if (Array.isArray(batch) && batch.length > 0) {
            setEvents((prev) => mergeEvents(prev, batch));
          }
        } catch {
          /* ignore */
        }
      };
      inst.onerror = () => {
        if (cancelled) return;
        // Safari may fire onerror while the stream is still open; do not close immediately.
        if (errDebounce !== undefined) window.clearTimeout(errDebounce);
        errDebounce = window.setTimeout(() => {
          errDebounce = undefined;
          if (cancelled) return;
          if (inst.readyState === EventSource.OPEN) return;
          setStreamOk(false);
          inst.close();
          if (es === inst) es = null;
          retry = window.setTimeout(connect, 4000);
        }, 1500);
      };
    };
    connect();
    return () => {
      cancelled = true;
      if (retry !== undefined) window.clearTimeout(retry);
      if (errDebounce !== undefined) window.clearTimeout(errDebounce);
      es?.close();
    };
  }, [sensorFilter, GW]);

  return (
    <div className="app">
      <header>
        <h1>Seismic — dashboard</h1>
        <p className="muted">
          PostgreSQL events: <strong>SSE</strong>{" "}
          {streamOk === false ? (
            <span className="error">(stream error — use &quot;Refresh now&quot;)</span>
          ) : (
            <span>+ initial load</span>
          )}
          .{" "}
          {GW ? (
            <>
              Gateway: <a href={GW}>{GW}</a>
            </>
          ) : (
            <>
              API on <strong>same origin</strong> (nginx/Vite → gateway). Direct test:{" "}
              <a href="http://localhost:8090/health">localhost:8090</a>
            </>
          )}
        </p>
      </header>

      <section className="panel">
        <h2>Processing replicas</h2>
        <div className="replicas">
          {replicas.map((r) => (
            <div key={r.url} className={`chip ${r.ok ? "ok" : "bad"}`}>
              {r.url.replace(/^https?:\/\//, "")} —{" "}
              {r.ok ? "online" : r.error ?? "offline"}
            </div>
          ))}
          {replicas.length === 0 && (
            <span className="muted">No replica data yet.</span>
          )}
        </div>
        <p className="muted small">
          The gateway uses round-robin + failover on{" "}
          <code>/api/processing/recent-events</code> (header{" "}
          <code>X-Processing-Replica</code>).
        </p>
      </section>

      <section className="panel">
        <h2>Persisted events (PostgreSQL)</h2>
        <div className="row">
          <label>
            Filter sensor{" "}
            <input
              value={sensorFilter}
              onChange={(e) => setSensorFilter(e.target.value)}
              placeholder="e.g. sensor-01"
            />
          </label>
          <button type="button" onClick={() => void loadEventsOnce()}>
            Refresh now (REST)
          </button>
        </div>
        {err && <p className="error">{err}</p>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time (UTC)</th>
                <th>Sensor</th>
                <th>Class</th>
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
            <p className="muted">No events in table (or DB still empty).</p>
          )}
        </div>
      </section>

      <section className="panel">
        <h2>Latest in-RAM classifications (replica via gateway)</h2>
        <p className="muted small">
          Data from the replica chosen by the gateway (round-robin); does not replace
          the DB.
          {ramSourceUrl && (
            <>
              {" "}
              <strong>Last request source:</strong>{" "}
              <code>{ramSourceUrl.replace(/^https?:\/\//, "")}</code>
            </>
          )}
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Sensor</th>
                <th>Class</th>
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
            <p className="muted">No data or replicas unreachable.</p>
          )}
        </div>
      </section>
    </div>
  );
}
