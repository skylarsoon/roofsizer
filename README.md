# PitchPoint

**Address in. Roof measured. Quote ready.**

PitchPoint is a hackathon product shell for AI-powered roof measurement and quote preparation. The demo goal is simple: a contractor enters or selects an address, sees the measured roof, reviews confidence and assumptions, then gets a customer-ready estimate/report.

The accuracy engine is owned separately. This app should consume engine outputs and present them clearly; it should not change scenario logic, pitch logic, building selection, scoring, benchmark calculations, or address-specific behavior.

## What It Does

- Shows a polished customer-facing roof measurement experience.
- Displays satellite imagery, selected roof/footprint overlays, predicted roof sqft, pitch, confidence, warnings, and quote ranges.
- Presents measurement math so the result feels explainable.
- Supports report-ready output for contractors.
- Leaves accuracy decisions to the backend/pipeline artifacts.

## Product Flow

1. Contractor enters or selects a property address.
2. Backend accuracy pipeline produces output artifacts.
3. Frontend loads the prediction, satellite image, overlay, and report links.
4. PitchPoint displays roof area, squares, pitch, line items, estimate range, warnings, and assumptions.
5. Contractor exports or opens a report for customer review.

## Accuracy Engine Boundary

PitchPoint must consume pipeline outputs. It must not recalculate or mutate measurement logic.

Do not modify accuracy behavior in:

- `src/pipeline.py`
- `src/scenarios.py`
- `src/evaluate.py`
- `src/diagnose.py`
- `src/select_building.py`
- `src/pitch.py`
- `src/geometry_utils.py`

Frontend/product code may read these outputs when available:

- `prediction.json`
- `satellite.png`
- `footprints.geojson`
- `selected.geojson`
- `top_candidates.geojson`
- `leaderboard.csv`
- `scenario_summary.csv`
- `dataset_summary.csv`
- `summary.md`
- `pattern_analysis.md`
- `recommended_scenario.md`
- `submission.json`

If an artifact is missing, the UI should show a friendly placeholder instead of crashing.

## Frontend

The current frontend is a standalone React + Vite app.

```bash
npm install
npm run dev
```

Production build:

```bash
npm run build
```

Google Places autocomplete is optional. To enable it, create `.env` from `.env.example` and set:

```bash
VITE_GOOGLE_MAPS_API_KEY=your_key_here
```

If the key is missing or the Google Maps SDK fails to load, the address field remains a normal text input.

## Backend

The current backend is FastAPI-based.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload
```

Server URL:

```text
http://127.0.0.1:8000
```

## Target API Shape For React

The frontend mock data should eventually be replaced by an endpoint that maps pipeline artifacts into this shape:

```json
{
  "sqft": 2443,
  "footprintSqft": 2120,
  "squares": 24.4,
  "squaresWithWaste": 28.1,
  "pitch": "6:12",
  "pitchMultiplier": 1.118,
  "pixelArea": 1847,
  "gsd": 0.0024,
  "confidence": 0.91,
  "manualReviewNeeded": false,
  "warnings": [],
  "satelliteImageUrl": "/outputs/.../satellite.png",
  "overlayImageUrl": "/outputs/.../overlay_selected.png",
  "reportUrl": "/outputs/.../report.html",
  "lineItems": {
    "eaves": 187,
    "rakes": 101,
    "ridge": 26,
    "hips": 101,
    "valleys": 40
  },
  "estimateLow": 8200,
  "estimateHigh": 13400
}
```

## Estimate Preview

PitchPoint may calculate a preliminary estimate from predicted roof sqft, but the roof measurement itself must come from the accuracy pipeline.

Suggested estimate defaults:

- Roofing squares: `predicted_sqft / 100`
- Waste factor: align with the final demo convention before judging
- Low/high range: contractor-configurable price per square
- Disclaimer: estimate is preliminary and should be reviewed by a roofing professional

## Report Output

Customer-facing reports should include:

- Property address
- Predicted roof sqft
- Footprint sqft
- Pitch used and pitch multiplier
- Confidence score
- Manual review needed
- Warnings
- Satellite image
- Overlay image if available
- Selected polygon artifact path
- Calculation formula
- Estimate preview
- Assumptions and disclaimer

Formula:

```text
Roof Sqft = Footprint Sqft × Pitch Multiplier
```

## Accuracy Lab

The demo should also tell the engineering story. When benchmark artifacts exist, PitchPoint should expose:

- Recommended scenario
- Leaderboard
- Scenario summary
- Dataset summary
- Worst cases
- Pattern analysis
- Decision log
- Submission outputs

This proves the team measured, compared, and iterated instead of guessing.

## Repository Layout

```text
PitchPoint/
├── main.py
├── requirements.txt
├── controllers/
├── core/
├── models/
├── routers/
├── services/
├── sample/
├── src/
│   ├── App.jsx
│   ├── InputPanel.jsx
│   ├── ResultsPanel.jsx
│   └── ...
├── README.md
├── APPROACH.md
└── DEMO_SCRIPT.md
```

## Demo Priorities

1. Show the end-to-end customer story: address, roof measurement, quote/report.
2. Show trust: imagery, selected structure, confidence, warnings, assumptions.
3. Show accuracy discipline: leaderboard, scenarios, worst cases, measured iteration.
4. Keep the UI clean, serious, and contractor-friendly.

## Known Limitations

- The React app currently uses mock data until the FastAPI integration endpoint is wired.
- Overlay imagery is currently demo-styled in the frontend.
- Final accuracy claims should not be added until benchmark artifacts are available.
- Estimate ranges are preliminary and should be reviewed by a roofing professional.

## Prompting Convention

When prompting the coding agent for next steps, start prompts with:

```text
Reference: @cursor.md
```
