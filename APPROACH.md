# PitchPoint — Approach (≤200 words)

**PitchPoint** — address-in / roof-sqft-out via a multi-source synthesizer pipeline.

**Stack.** Python (geopandas, shapely, pyproj) + FastAPI backend; React + Vite frontend.

**Models.** Two frontier multimodal LLMs are used in parallel as candidate pitch estimators (each given 3 zoom levels × 3 shots; per-property median is taken). A third multimodal LLM call acts as a **synthesizer** — it reads a per-property evidence dossier (5 candidate pitches + raw context including roof-segment data, polygon comparisons, and a ground-level Street View image) and commits to a final rise:12 pitch and roof sqft with explicit reasoning.

**Data sources.** Static aerial imagery (zoom 19/20/21), public building footprint datasets, Solar API roof-segment analysis, ground-level Street View, geocoding + address validation.

**Novelty.** The synthesizer doesn't just pick one estimate — it reads a markdown dossier of *all* evidence (with images) and commits to a path (direct slanted-area vs. footprint × pitch) with audit-traced reasoning per property.

**Validation.** 100 real residential properties: **MAPE 13.6%**, 100/100 scoreable, no manual review needed. Every prediction has a per-property evidence dossier saved as artifacts.

(199 words)
