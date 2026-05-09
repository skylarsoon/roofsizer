# PitchPoint

**Address in. Roof measured. Quote ready.**

PitchPoint takes a residential property address and returns total roof square footage with audit-traced reasoning. It orchestrates multiple imagery and footprint sources behind a single multimodal-LLM **synthesizer** that commits to a final pitch and area per property.

Validated on 100 real residential properties: **MAPE 13.6%**, 100/100 scoreable, no manual review required. See `SUBMISSION.md` for the five hackathon test addresses and `APPROACH.md` for the 199-word approach summary.

## How It Works

For each address the backend runs `s_synthesizer`:

1. **Evidence gathering** (in parallel per property): regional pitch lookup, climate-region classifier, ground-level pitch read, two independent multimodal-vision pitch estimates (3 zoom levels × 3 shots, median), aerial roof-segment analysis, plus raw context (public footprints, address validation, satellite imagery at zoom 19/20/21, ground-level imagery).
2. **Synthesizer** — one multimodal LLM call reads the per-property evidence dossier (markdown + images) and commits to either **Path A** (direct slanted roof area) or **Path B** (footprint × pitch multiplier), with explicit reasoning.
3. **API mapper** strips raw vendor names from the response — the UI shows PitchPoint-branded labels only. Per-property cache files keep the raw dossier for audit.

## Repository Layout

```
pitchpoint/
├── src/                        # React + Vite UI
│   ├── App.jsx                 # fetches /api/analyze
│   ├── ImagePreview.jsx        # satellite image + roof outline overlay
│   ├── InputPanel.jsx          # address autocomplete + math typewriter
│   ├── SynthesizerPanel.jsx    # path badge + sanitized sources + reasoning
│   ├── FirstPassPanel.jsx      # candidate table + raw dossier modal
│   └── lib/projectGeoJson.js   # lat/lng → SVG pixel projection
├── server/
│   ├── api.py                  # FastAPI bridge: /api/analyze, /api/image/{slug}/{name}
│   ├── run_pipeline.py         # CLI entrypoint to warm the cache for one address
│   ├── roofer/                 # synthesizer pipeline
│   ├── data/benchmarks.json    # 5 test + 5 calibration addresses
│   └── cache/s_synthesizer/    # pre-warmed per-property artifacts (instant demo)
├── docs/screenshots/           # one screenshot per test address
├── scripts/warm_cache.sh       # pre-runs synthesizer on the test addresses
├── SUBMISSION.md               # the 5 final sqft numbers
├── APPROACH.md                 # 199-word approach summary
└── Makefile                    # install / warm / dev
```

## Run It

```bash
make install          # one-time: venv + npm install
make warm             # pre-runs synthesizer on the 5 test addresses
make dev              # parallel: uvicorn (:8000) + vite (:5173)
# Open http://localhost:5173 and paste any of the 5 test addresses.
```

Live arbitrary addresses also work — the API falls through to a live pipeline run on cache miss (~30–60 s per property).

`.env.example` lists the keys required.

## API

| Endpoint | Description |
|---|---|
| `GET /api/analyze?address=…` | Sanitized JSON: sqft, footprintSqft, pitch, multiplier, confidence, synthesizer reasoning, first-pass candidates table, satellite + GeoJSON URLs |
| `GET /api/image/{slug}/{name}` | Static proxy for `satellite_z20.png`, `selected.geojson`, `streetview.jpg`, `dossier.md` |
| `GET /api/health` | Liveness probe |

## Sample Outputs

Five screenshots, one per official test address — UI showing satellite image with roof outline overlay, sqft / squares / pitch metric cards, synthesizer panel, and first-pass evidence panel.

| Address | Sqft | Screenshot |
|---|---:|---|
| 3561 E 102nd Ct, Thornton, CO 80229       | 2,081 | [docs/screenshots/3561-e-102nd-ct-thornton-co-80229.png](docs/screenshots/3561-e-102nd-ct-thornton-co-80229.png) |
| 1612 S Canton Ave, Springfield, MO 65802  | 2,757 | [docs/screenshots/1612-s-canton-ave-springfield-mo-65802.png](docs/screenshots/1612-s-canton-ave-springfield-mo-65802.png) |
| 6310 Laguna Bay Court, Houston, TX 77041  | 4,186 | [docs/screenshots/6310-laguna-bay-court-houston-tx-77041.png](docs/screenshots/6310-laguna-bay-court-houston-tx-77041.png) |
| 3820 E Rosebrier St, Springfield, MO 65809| 5,566 | [docs/screenshots/3820-e-rosebrier-st-springfield-mo-65809.png](docs/screenshots/3820-e-rosebrier-st-springfield-mo-65809.png) |
| 1261 20th Street, Newport News, VA 23607  | 6,118 | [docs/screenshots/1261-20th-street-newport-news-va-23607.png](docs/screenshots/1261-20th-street-newport-news-va-23607.png) |

## Validation

| Scenario | Scoreable | MAPE |
|---|---:|---:|
| `s_resilient_v3` (BUY baseline)  | 89 / 100  | 10.69% |
| **`s_synthesizer` (BUILD)**      | **100 / 100** | **13.63%** |

On the 89 properties both score, the synthesizer matches the BUY baseline within ±1pp on 88 / 89.
