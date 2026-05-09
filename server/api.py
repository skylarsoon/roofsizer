"""PitchPoint FastAPI bridge.

Two endpoints, both serve the React frontend:

    GET /api/analyze?address=...   — sanitized JSON for the UI
    GET /api/image/{slug}/{name}   — static proxy for satellite/streetview/geojson/dossier

The API mapper strips raw vendor names (Solar / GPT / Gemini / Microsoft / OpenStreetMap)
from the response. Raw values remain in the on-disk cache files for audit.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import certifi as _certifi

for _v in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
    os.environ.setdefault(_v, _certifi.where())

SERVER_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_ROOT))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from roofer.cache import Cache  # noqa: E402
from roofer.config import load_config  # noqa: E402
from roofer.pipeline import address_slug, run_pipeline  # noqa: E402
from roofer.scenarios import get_scenario  # noqa: E402

CACHE_ROOT = SERVER_ROOT / "cache"
CACHE_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PitchPoint API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# -------- Sanitized labels (the UI never sees vendor names) -------- #

FOOTPRINT_LABEL = {
    "solar_whole":  "PitchPoint aerial roof analysis",
    "solar_ground": "PitchPoint aerial footprint",
    "ms":           "Public building footprints",
    "osm":          "Public building footprints",
    "sam":          "PitchPoint segmentation",
    "synthesis":    "PitchPoint synthesizer composite",
}

PITCH_LABEL = {
    "solar_pitch":  "PitchPoint multi-segment pitch",
    "solar_direct": "PitchPoint multi-segment pitch",
    "gpt_multi":    "Multi-zoom vision (3 shots, median)",
    "gemini_multi": "Multi-zoom vision (3 shots, median)",
    "streetview":   "Side-view ground analysis",
    "regional":     "Regional pitch lookup",
    "llm_regional": "Climate-region classifier",
    "synthesis":    "PitchPoint synthesizer composite",
    "default":      "Default pitch",
    "calibration_mean": "Calibrated default pitch",
}


_VENDOR_REWRITES = [
    (re.compile(r"\bsolar\s+whole[A-Za-z]*stats?\b", re.IGNORECASE), "PitchPoint aerial roof analysis"),
    (re.compile(r"\bwhole[A-Za-z]*stats?\b", re.IGNORECASE), "aerial roof analysis"),
    (re.compile(r"\bgoogle\s+solar\s+api\b", re.IGNORECASE), "PitchPoint aerial analysis"),
    (re.compile(r"\bsolar\s+api\b", re.IGNORECASE), "PitchPoint aerial analysis"),
    (re.compile(r"\bgoogle\s+solar\b", re.IGNORECASE), "PitchPoint aerial analysis"),
    (re.compile(r"\bsolar\b", re.IGNORECASE), "aerial"),
    (re.compile(r"\bopenai\b", re.IGNORECASE), "vision model"),
    (re.compile(r"\bgpt[-\s]?\d*(?:\.\d+)?\b", re.IGNORECASE), "vision model"),
    (re.compile(r"\bgpt\b", re.IGNORECASE), "vision model"),
    (re.compile(r"\bgemini\s+\d+(?:\.\d+)?\s*pro\b", re.IGNORECASE), "vision model"),
    (re.compile(r"\bgemini\b", re.IGNORECASE), "vision model"),
    (re.compile(r"\bmicrosoft\s+building\s+footprints?\b", re.IGNORECASE), "public footprints"),
    (re.compile(r"\bmicrosoft\b", re.IGNORECASE), "public"),
    (re.compile(r"\bopenstreetmap\b", re.IGNORECASE), "public"),
    (re.compile(r"\bosm\b", re.IGNORECASE), "public"),
    (re.compile(r"\bgoogle\s+street\s*view\b", re.IGNORECASE), "ground-level imagery"),
    (re.compile(r"\bstreet\s*view\b", re.IGNORECASE), "ground-level imagery"),
    (re.compile(r"\bgoogle\s+maps?\b", re.IGNORECASE), "satellite imagery"),
    (re.compile(r"\bgoogle\b", re.IGNORECASE), "satellite imagery"),
]


def _scrub_vendors(text: Optional[str]) -> str:
    if not text:
        return ""
    out = text
    for pattern, repl in _VENDOR_REWRITES:
        out = pattern.sub(repl, out)
    return out


def _sanitize_synth(synth: dict) -> dict:
    """Map raw vendor strings to PitchPoint-branded labels for the FE."""
    if not isinstance(synth, dict):
        return {}
    raw_fp = synth.get("footprint_source") or ""
    raw_pitch = synth.get("pitch_source") or ""
    return {
        "path": synth.get("path"),
        "pathLabel": (
            "Direct slanted-area" if synth.get("path") == "A_solar_direct"
            else "Footprint × Pitch"
        ),
        "footprintSource": FOOTPRINT_LABEL.get(raw_fp, "PitchPoint analysis"),
        "pitchSource":     PITCH_LABEL.get(raw_pitch, "PitchPoint analysis"),
        "reasoning":       _scrub_vendors(synth.get("reasoning")),
        # Intentionally drop: raw footprint_source/pitch_source, synthesizer_provider,
        # raw response, model name. Audit trail stays in cache files.
    }


def _sanitize_candidates(evidence: dict) -> list[dict]:
    """Build the FE 'first pass' candidates table without vendor names."""
    cands = (evidence or {}).get("candidates") or {}
    out = []
    for raw_name, est in cands.items():
        if est is None:
            continue
        # raw_name is one of: regional, llm_regional, streetview, gpt_multi, gemini_multi
        first_clause = (est.get("reasoning") or "").split(";")[0][:240]
        out.append({
            "label":      PITCH_LABEL.get(raw_name, raw_name.replace("_", " ").title()),
            "pitch":      f"{int(est.get('rise', 0))}:12" if est.get("rise") is not None else "—",
            "confidence": float(est.get("confidence") or 0.0),
            "reasoning":  _scrub_vendors(first_clause),
        })
    # Sort by confidence desc for nicer display
    out.sort(key=lambda c: -c["confidence"])
    return out


def _footprint_candidates(evidence: dict) -> dict:
    raw = (evidence or {}).get("raw_context") or {}
    out = {}
    ms = raw.get("ms") or {}
    osm = raw.get("osm") or {}
    if ms.get("count"):
        out["public_a"] = {
            "label": "Public footprint A",
            "areaSqft": ms.get("closest_area_sqft"),
            "distanceM": ms.get("closest_distance_m"),
            "polygonCount": ms.get("count"),
        }
    if osm.get("count"):
        out["public_b"] = {
            "label": "Public footprint B",
            "areaSqft": osm.get("closest_area_sqft"),
            "distanceM": osm.get("closest_distance_m"),
            "polygonCount": osm.get("count"),
        }
    # Solar/aerial — surfaced under our own brand name
    sd = raw.get("solar") or {}
    if sd.get("available"):
        out["aerial"] = {
            "label": "PitchPoint aerial roof analysis",
            "areaSqft": sd.get("whole_roof_area_sqft"),
            "groundAreaSqft": sd.get("ground_area_sqft"),
            "segments": sd.get("roof_segment_count"),
            "weightedPitchDeg": sd.get("weighted_pitch_deg"),
        }
    return out


def _pitch_label_short(pitch_used_raw: Optional[str]) -> str:
    """Strip parenthetical suffixes from labels like '6:12 (gemini median of 3 shots)'."""
    if not pitch_used_raw:
        return "—"
    m = re.match(r"\s*([0-9.]+)\s*[:/]\s*(\d+)", pitch_used_raw)
    if m:
        rise, run = m.group(1), m.group(2)
        try:
            r = float(rise)
            rise = str(int(r)) if r.is_integer() else str(r)
        except ValueError:
            pass
        return f"{rise}:{run}"
    return pitch_used_raw.split(" ")[0]


def _build_response(slug: str, prediction: dict, synthesizer_output: dict, evidence: dict, address: str) -> dict:
    sqft = prediction.get("predicted_sqft")
    fp_sqft = prediction.get("footprint_sqft")
    pitch_mult = prediction.get("pitch_multiplier") or 1.0
    pitch_label_raw = prediction.get("pitch_used") or ""
    pitch_short = _pitch_label_short(pitch_label_raw)

    squares = round((sqft or 0) / 100.0, 1) if sqft else None
    squares_w_waste = round((sqft or 0) / 100.0 * 1.15, 1) if sqft else None

    response = {
        "slug": slug,
        "address": address,
        "geocode": {
            "lat": prediction.get("lat"),
            "lng": prediction.get("lng"),
        },
        "sqft": sqft,
        "footprintSqft": fp_sqft,
        "squares": squares,
        "squaresWithWaste": squares_w_waste,
        "pitch": pitch_short,
        "pitchMultiplier": pitch_mult,
        "confidence": prediction.get("confidence"),
        "manualReviewNeeded": prediction.get("manual_review_needed", False),
        "warnings": [
            w for w in (prediction.get("warnings") or [])
            # Strip warnings that name vendors
            if not re.search(r"(?i)\b(solar|gpt|gemini|openai|microsoft|google|osm|sam)\b", str(w))
        ],
        "satelliteImageUrl": f"/api/image/{slug}/satellite_z20.png",
        "footprintGeoJsonUrl": f"/api/image/{slug}/selected.geojson",
        "synthesizer": _sanitize_synth(synthesizer_output),
        "firstPass": {
            "candidates": _sanitize_candidates(evidence),
            "footprints": _footprint_candidates(evidence),
        },
        # Naive estimate range (placeholder pricing); real line items can land later.
        "estimateLow": round((squares_w_waste or 0) * 350) if squares_w_waste else None,
        "estimateHigh": round((squares_w_waste or 0) * 575) if squares_w_waste else None,
    }
    return response


def _read_cached(slug: str, address: str) -> Optional[dict]:
    record_dir = CACHE_ROOT / "s_synthesizer" / slug
    pred_path = record_dir / "prediction.json"
    if not pred_path.exists():
        return None
    try:
        prediction = json.loads(pred_path.read_text())
    except Exception:
        return None
    synth_path = record_dir / "synthesizer_output.json"
    synth = json.loads(synth_path.read_text()) if synth_path.exists() else {}
    evidence_path = record_dir / "evidence.json"
    evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    return _build_response(slug, prediction, synth, evidence, address)


def _live_run(address: str) -> dict:
    cfg = load_config(strict=True)
    scenario = get_scenario("s_synthesizer")
    cache = Cache(CACHE_ROOT, refresh=False)
    record = {"id": "live", "address": address, "dataset": "live"}
    res = run_pipeline(
        record=record, scenario=scenario, cfg=cfg, cache=cache,
        output_dir=CACHE_ROOT, run_id="s_synthesizer",
    )
    pred_dict = res.to_dict()
    slug = address_slug(address)
    record_dir = CACHE_ROOT / "s_synthesizer" / slug
    synth_path = record_dir / "synthesizer_output.json"
    synth = json.loads(synth_path.read_text()) if synth_path.exists() else {}
    evidence_path = record_dir / "evidence.json"
    evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    return _build_response(slug, pred_dict, synth, evidence, address)


@app.get("/api/analyze")
def analyze(address: str = Query(..., min_length=5)) -> JSONResponse:
    slug = address_slug(address)
    cached = _read_cached(slug, address)
    if cached is not None:
        cached["cacheHit"] = True
        return JSONResponse(cached)
    try:
        live = _live_run(address)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pipeline failed: {e}")
    live["cacheHit"] = False
    return JSONResponse(live)


@app.get("/api/image/{slug}/{name}")
def get_artifact(slug: str, name: str):
    # Whitelist filenames for safety
    allowed = {
        "satellite_z19.png", "satellite_z20.png", "satellite_z21.png",
        "satellite.png",  # legacy
        "selected.geojson", "footprints.geojson", "top_candidates.geojson",
        "streetview.jpg", "dossier.md",
    }
    if name not in allowed:
        raise HTTPException(status_code=404, detail="not allowed")
    path = CACHE_ROOT / "s_synthesizer" / slug / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="not found")
    media = (
        "image/png" if name.endswith(".png")
        else "image/jpeg" if name.endswith(".jpg")
        else "application/json" if name.endswith(".geojson")
        else "text/markdown"
    )
    headers = {"Cache-Control": "public, max-age=86400"}
    return FileResponse(path, media_type=media, headers=headers)


@app.get("/api/health")
def health():
    return {"status": "ok"}
