# Cursor Working Reference: PitchPoint

## Project Identity

- Project: `PitchPoint`
- Tagline: `Address in. Roof measured. Quote ready.`
- Goal: turn an address and accuracy-engine outputs into a roof measurement report and contractor-ready estimate
- Audience: roofing contractors who need fast, explainable measurement output
- Hackathon context: JobNimbus track

## Product Story

Commercial roof measurement reports can cost contractors time and money before they can quote a job. PitchPoint wraps the accuracy engine in a polished product flow:

1. User enters or selects an address.
2. Backend/pipeline creates measurement artifacts.
3. UI shows satellite imagery, selected structure, predicted roof sqft, confidence, warnings, and estimate line items.
4. Customer-ready report becomes available.

## Product Shell Boundary

Accuracy work is owned separately. Product/frontend code should consume outputs, not recalculate core measurements.

Read these artifacts when available:

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

If a file is missing, fail gracefully with a friendly message.

## Core Accuracy Rules

Do not change pitch logic, building selection logic, scenario ranking, scoring logic, benchmark calculations, or address-specific behavior from product/UI work.

Do not modify these accuracy files unless explicitly asked:

- `src/pipeline.py`
- `src/scenarios.py`
- `src/evaluate.py`
- `src/diagnose.py`
- `src/select_building.py`
- `src/pitch.py`
- `src/geometry_utils.py`

## Measurement Constraint

Roof footprint area is not the same as roof surface area.

- `roof_area = footprint_area * pitch_multiplier`
- `pitch_multiplier = sqrt(1 + (rise / run)^2)`
- Default pitch is `6:12`, so multiplier is approximately `1.118`

Always show measurement math for explainability, but do not fabricate measurements or accuracy numbers.

## Current Tech Stack

- Backend: Python `3.11`, FastAPI, router/controller/service architecture
- Accuracy engine: owned separately; consume its artifacts
- Frontend: React + Vite product demo
- Styling: plain CSS, no component library
- No database
- No authentication

## Current Frontend Structure

```text
/src
  App.jsx
  Navbar.jsx
  InputPanel.jsx
  ResultsPanel.jsx
  ImagePreview.jsx
  MetricCard.jsx
  LineItems.jsx
  EstimateBar.jsx
  Toast.jsx
  index.css
```

## Product Responsibilities

- Display address analysis result
- Show satellite image and overlay when available
- Show roof sqft, squares, pitch, confidence, warnings, and manual review status
- Show estimate preview
- Link to or render customer report
- Show accuracy lab artifacts when available
- Show submission outputs when available

## Hard Implementation Rules

- Do not modify core accuracy files unless explicitly asked.
- Do not fabricate measurements or accuracy numbers.
- Do not hardcode address-specific fixes.
- Do not claim PDF export exists if only HTML exists.
- Do not block the demo on perfect overlays; use graceful placeholders.
- Keep customer-facing copy contractor-friendly and trustworthy.

## Roofing Line Items

- Eaves: bottom horizontal perimeter edges
- Rakes: sloped perimeter edges at gable ends
- Ridge: top horizontal peak lines
- Hips: diagonal peak intersections
- Valleys: interior concave facet intersections
- Squares: `total_roof_sqft / 100`

## Frontend Result Contract

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

## Demo Story

1. Contractors need fast roof estimates from an address.
2. PitchPoint starts with an address.
3. It shows satellite/property context and selected roof evidence.
4. It presents predicted roof sqft, pitch, confidence, warnings, and estimate range.
5. The Accuracy Lab proves scenarios were benchmarked and measured.
6. Final outputs are organized for submission and customer review.

## Prompting Convention

For future implementation prompts, start with:

```text
Reference: @cursor.md
```
