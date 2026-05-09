# Cursor Working Reference: RoofScope

## Project Identity

- Project: `RoofScope` (JobNimbus Roof Sizer for hackathon use)
- Goal: turn a single aerial residential image into a roof measurement report and contractor-ready estimate
- Audience: roofing contractors who need fast, explainable measurement output
- Hackathon context: JobNimbus track

## Problem Statement

Commercial roof measurement reports (EagleView, Geospan) can cost about `$30-$150` per property. This project automates that workflow:

1. User uploads an aerial photo
2. User clicks the roof as a segmentation prompt
3. System returns roof geometry, square footage, and estimate line items in seconds

## End-to-End Pipeline

1. Upload aerial property image
2. Capture user prompt click on roof
3. Run SAM 2 prompted segmentation
4. Extract roof polygon and pixel geometry with OpenCV
5. Convert pixels to feet using GSD calibration
6. Apply pitch multiplier to convert footprint area to true roof area
7. Derive roofing line items from polygon edge geometry
8. Produce structured estimate with quantity + price ranges

## Most Important Technical Constraint

Roof footprint area is not the same as roof surface area.

- Formula:
  - `roof_area = footprint_area * pitch_multiplier`
  - `pitch_multiplier = sqrt(1 + (rise / run)^2)`
- Default pitch is `6:12`, so multiplier is approximately `1.118`
- This conversion is a critical correctness requirement and a common failure mode

## Evaluation Criteria

- Compare total roof sqft output against commercial references (EagleView/Geospan)
- Practical tolerance target: within about `5-10%`
- Output must be contractor-usable (line items + estimate), not just raw area
- Judging dimensions: accuracy, product usefulness, UX, code craft, demo quality

## Tech Stack

- Backend: Python `3.11`, FastAPI, router/controller/service architecture
- Segmentation: SAM 2 (`sam2` package, `SAM2ImagePredictor`)
- Geometry: OpenCV (`findContours`, `arcLength`, `contourArea`) + Shapely
- Frontend: React preferred (clean HTML fallback acceptable)
- No database
- No authentication

## Target Structure

```text
/backend
  /routers
  /controllers
  /services       # sam.py, geometry.py, gsd.py, estimate.py
  main.py
  requirements.txt
/frontend
```

## Core Logic Responsibilities

- `sam.py`: load SAM 2 once at startup, run prompted segmentation, return binary mask
- `geometry.py`: convert mask to polygon, pixel area, and classified edges
- `gsd.py`: convert pixel geometry to feet via EXIF or user-drawn reference object
- `estimate.py`: pitch-adjust area, compute squares, line items, materials, and cost range

## Hard Implementation Rules

- SAM 2 must run in prompted mode only (point or box), never automatic mode
- Load SAM 2 once on startup (do not load per request)
- Default pitch is `6:12` (multiplier `1.118`) unless user overrides
- GSD fallback is required when EXIF is missing:
  - user draws reference line over known object (car ~15 ft, lane ~12 ft)
- Always show measurement math for explainability
- Never fabricate measurements

## Roofing Line Items

- Eaves: bottom horizontal perimeter edges (fascia interface)
- Rakes: sloped perimeter edges at gable ends
- Ridge: top horizontal peak lines
- Hips: diagonal peak intersections
- Valleys: interior concave facet intersections
- Squares: `total_roof_sqft / 100`

## Estimate JSON Contract

```json
{
  "roof_sqft": 2443,
  "squares": 24.43,
  "pitch": "6:12",
  "pitch_multiplier": 1.118,
  "line_items": {
    "eaves_ft": 187,
    "rakes_ft": 101,
    "ridge_ft": 26,
    "hip_ft": 101,
    "valleys_ft": 40
  },
  "materials": {
    "shingles_squares": 28.1,
    "drip_edge_ft": 288,
    "ridge_cap_ft": 127
  },
  "estimate": {
    "materials_low": 4200,
    "materials_high": 6800,
    "labor_low": 2400,
    "labor_high": 4800,
    "total_low": 6600,
    "total_high": 11600
  },
  "confidence": "high",
  "gsd_source": "exif"
}
```

## Validation Target

- Property: `21106 Kenswick Meadows Ct, Humble TX`
- Reference roof area: around `2,443 sqft` at `6:12` pitch
- Use as a pre-submission sanity check

## Suggested Build Order (20-Hour Budget)

1. FastAPI skeleton + `/upload`
2. SAM 2 integration (image -> mask)
3. OpenCV polygon extraction (mask -> geometry)
4. GSD calibration (pixel -> feet)
5. Pitch multiplier + roof sqft computation
6. Line item + estimate generation
7. Explainability overlay (edge labels + visible math)
8. Frontend flow (upload, click prompt, annotated result, estimate card)

## Prompting Convention

For future implementation prompts, start with:

- `Reference: @cursor.md`

This keeps project constraints and assumptions visible in every step.
