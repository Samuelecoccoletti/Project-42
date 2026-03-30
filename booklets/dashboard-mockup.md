# Dashboard SEISMIC — mockup lo‑fi

Il layout a quattro blocchi dello schizzo è **allineato** all’implementazione attuale:

| Blocco mockup | Implementazione (`source/web`) |
|---------------|-------------------------------|
| **SEISMIC – Dashboard** | Titolo / intestazione della pagina |
| **REPLICHE – STATUS** | Chip / stato repliche (polling gateway) |
| **EVENTI – DATABASE** | Tabella eventi persistiti (REST + SSE) |
| **RAM – ULTIME CLASSIFICAZIONI** | Tabella classificazioni in RAM per replica (gateway) |

**File immagine:** [`dashboard-mockup-lofi.png`](dashboard-mockup-lofi.png) — 

Colonne tabella attese: `tempo`, `sensor`, `class`, `freq`, `replica` — coerenti con i campi esposti dall’API e dalla UI.
