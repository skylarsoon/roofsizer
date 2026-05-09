# PitchPoint — JobNimbus AI Hackathon Submission

**Run date:** 2026-05-09
**Scenario:** `s_synthesizer` (multi-source evidence dossier → multimodal LLM synthesizer)
**Validation:** MAPE 13.6%, 100/100 scoreable, no manual review needed

## The five test addresses

| # | Address | Total roof sqft | Pitch | Confidence | Path |
|---|---|---:|---:|---:|---|
| 1 | 3561 E 102nd Ct, Thornton, CO 80229       | **2,081** | 9:12 | 1.00 | Direct slanted-area |
| 2 | 1612 S Canton Ave, Springfield, MO 65802  | **2,757** | 7:12 | 1.00 | Direct slanted-area |
| 3 | 6310 Laguna Bay Court, Houston, TX 77041  | **4,186** | 8:12 | 1.00 | Direct slanted-area |
| 4 | 3820 E Rosebrier St, Springfield, MO 65809| **5,566** | 6:12 | 1.00 | Direct slanted-area |
| 5 | 1261 20th Street, Newport News, VA 23607  | **6,118** | 4:12 | 1.00 | Direct slanted-area |

For all five, the synthesizer chose **Path A** (direct slanted roof area from PitchPoint aerial roof analysis with weighted per-segment pitch) over **Path B** (footprint × pitch multiplier). Pitches are reported as the rise:12 conversion of the weighted mean roof segment angle.

## How to reproduce

```bash
cd ~/Desktop/pitchpoint
make install            # one-time: venv + npm install
make warm               # pre-runs synthesizer on the 5 test addresses (~5 min cold, instant warm)
make dev                # parallel: uvicorn (:8000) + vite (:5173)
# Then open http://localhost:5173 and paste any of the 5 addresses.
```

To regenerate the numbers in this file:

```bash
cd ~/Desktop/pitchpoint
.venv/bin/python server/run_pipeline.py --address "3561 E 102nd Ct, Thornton, CO 80229"        --scenario s_synthesizer --output server/cache
.venv/bin/python server/run_pipeline.py --address "1612 S Canton Ave, Springfield, MO 65802"   --scenario s_synthesizer --output server/cache
.venv/bin/python server/run_pipeline.py --address "6310 Laguna Bay Court, Houston, TX 77041"   --scenario s_synthesizer --output server/cache
.venv/bin/python server/run_pipeline.py --address "3820 E Rosebrier St, Springfield, MO 65809" --scenario s_synthesizer --output server/cache
.venv/bin/python server/run_pipeline.py --address "1261 20th Street, Newport News, VA 23607"   --scenario s_synthesizer --output server/cache
```

Per-property artifacts (raw evidence dossier, synthesizer reasoning, satellite + Street View images, footprint GeoJSON) are saved under `server/cache/s_synthesizer/{slug}/`.

## Validation results (background)

`s_synthesizer` was validated on 100 real residential properties with measured ground-truth roof sqft:

| Scenario | Scoreable | MAPE | Notes |
|---|---:|---:|---|
| `s_resilient_v3` (BUY baseline) | 89 / 100 | 10.69% | Uses commercial measurement directly |
| **`s_synthesizer` (BUILD)**     | **100 / 100** | **13.63%** | Our orchestration; covers cases the BUY baseline abstains on |

On the 89 properties both score, the synthesizer matches the BUY baseline within ±1pp on 88 / 89.

## Screenshots

`docs/screenshots/{slug}.png` — one screenshot per test address showing the running UI: address input, satellite image with roof outline overlay, metric cards (sqft / squares / pitch), synthesizer decision panel, and first-pass evidence panel.
