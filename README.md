# RoofScope (JobNimbus Roof Sizer)

`RoofScope` is a web-based AI tool that turns an aerial residential property image into an explainable roof measurement report and contractor-ready estimate.

This project is built for the JobNimbus hackathon track.

## Problem

Roofing contractors often pay `$30-$150` per property for commercial measurement reports (for example, EagleView or Geospan). RoofScope aims to automate that workflow:

1. Contractor uploads an aerial photo
2. Contractor clicks the roof to prompt segmentation
3. System returns measured roof geometry, line items, and estimate ranges in seconds

## Pipeline

1. Upload aerial image
2. Capture click prompt on roof
3. Segment roof with SAM 2 in prompted mode
4. Extract polygon + geometry with OpenCV
5. Convert pixels to feet with GSD calibration
6. Convert footprint area to roof area using pitch multiplier
7. Derive roofing line items (eaves/rakes/ridge/hips/valleys)
8. Generate structured estimate output

## Critical Constraint: Roof Area vs Footprint Area

Top-down footprint area is not true roof surface area for pitched roofs.

- `roof_area = footprint_area * pitch_multiplier`
- `pitch_multiplier = sqrt(1 + (rise / run)^2)`
- Default pitch: `6:12`
- Default multiplier: `1.118`

This conversion is a hard requirement and the most common source of measurement bugs.

## Evaluation Targets

- Compare total sqft output against commercial references (EagleView/Geospan)
- Practical accuracy goal: within about `5-10%`
- Output must include usable contractor line items and estimate, not only sqft
- Judging dimensions: accuracy, product usefulness, UX, code craft, demo quality

## Current Stack

- Backend: Python `3.11`, FastAPI
- Architecture: router/controller/service-oriented layering
- Segmentation: SAM 2 (`sam2`, `SAM2ImagePredictor`)
- Geometry: OpenCV + Shapely
- Frontend: React preferred (or clean HTML fallback)
- No database, no auth

## Current Repository Layout

```text
JobNimbusRoofSizer/
├── main.py
├── requirements.txt
├── routers/
├── controllers/
├── models/
├── core/
└── sample/
```

## Target Service Responsibilities

- `sam.py`: load SAM 2 once at startup; run prompted segmentation; return binary mask
- `geometry.py`: convert mask to polygon/edges/area in pixels
- `gsd.py`: map pixels to feet via EXIF or user reference line fallback
- `estimate.py`: pitch-adjust area; compute squares, line items, materials, and cost ranges

## Non-Negotiable Implementation Rules

- Use SAM 2 in prompted mode only (point or box), never automatic mode
- Load SAM 2 once at app startup, never per request
- Default pitch is `6:12` (multiplier `1.118`) unless user overrides
- GSD must include fallback when EXIF is absent:
  - user draws reference line over known object (car ~15 ft, lane ~12 ft)
- Show measurement math in output/overlay for explainability
- Do not fabricate measurements

## Required Roofing Line Items

- Eaves
- Rakes
- Ridge
- Hips
- Valleys
- Total Squares (`roof_sqft / 100`)

## Estimate Output Contract

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

## Reference Validation Property

- `21106 Kenswick Meadows Ct, Humble TX`
- Expected roof total at `6:12`: about `2,443 sqft`
- Use as a gut-check before submission/demo

## Suggested Build Order (20-Hour Budget)

1. FastAPI skeleton + `/upload` endpoint
2. SAM 2 integration (image -> binary mask)
3. OpenCV polygon extraction (mask -> geometry)
4. GSD calibration (pixels -> feet)
5. Pitch multiplier + sqft conversion
6. Line item extraction + estimate generation
7. Explainability overlay (annotated edges + visible math)
8. Frontend flow (upload, click prompt, result overlay, estimate card)

## Run Locally

### 1) Confirm Python

```bash
python3.11 --version
```

### 2) Create and activate virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

The first server startup downloads SAM 2 weights once and caches them locally.

### 4) Start backend

```bash
.venv/bin/uvicorn main:app --reload
```

Server URL: `http://127.0.0.1:8000`

## API: Upload Endpoint

- Endpoint: `POST /upload`
- Input: image file (`jpg` or `png`)
- Returns:
  - upload filename
  - image shape
  - `mask_b64` (white = roof, black = background)
  - `iou_score`

Example:

```json
{
  "status": "ok",
  "filename": "roof.jpg",
  "image_shape": [1024, 768, 3],
  "mask_b64": "iVBORw0KGgo...",
  "iou_score": 0.91
}
```

## Prompting Convention

When prompting the coding agent for next steps, start prompts with:

`Reference: @cursor.md`
