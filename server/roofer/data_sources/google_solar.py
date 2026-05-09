"""Google Solar API — coverage probe + measurement extractor.

`fetch_solar_coverage` (Tier A): records availability metadata only.
`fetch_solar_building_data` (Tier C): returns per-segment pitch + whole-roof
area for use as a measurement source.

Note: `solarPotential.wholeRoofStats.areaMeters2` is the SLANTED roof area
(actual surface area accounting for pitch), exactly what we want to predict.
`roofSegmentStats[*].pitchDegrees` gives per-facet pitch — we compute an
area-weighted mean for use with non-Solar footprints (MS/OSM)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from ..cache import Cache, _addr_hash

BUILDING_INSIGHTS_URL = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
DATA_LAYERS_URL = "https://solar.googleapis.com/v1/dataLayers:get"


def fetch_solar_coverage(
    address: str,
    lat: float,
    lng: float,
    api_key: str,
    cache: Optional[Cache] = None,
    refresh: bool = False,
) -> dict:
    """Probe Solar APIs and return what we got. Never raises — any error
    becomes part of the returned dict.

    Returns: {
      address, lat, lng,
      solar_available: bool,
      building_insights_found: bool,
      solar_center_lat, solar_center_lng,
      imagery_date,
      roof_segment_data_available: bool,
      data_layers_available: bool,
      dsm_available: bool,
      mask_available: bool,
      error: str | None,
      raw_building_insights_keys: list (for debugging),
    }
    """
    cache_dir: Optional[Path] = None
    cache_path: Optional[Path] = None
    if cache is not None:
        cache_dir = cache.paths.root / "solar"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{_addr_hash(address)}.json"
        if not refresh and cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text())
                if payload.get("_schema_version") == 1:
                    return payload["data"]
            except Exception:
                pass

    out: dict[str, Any] = {
        "address": address, "lat": lat, "lng": lng,
        "solar_available": False,
        "building_insights_found": False,
        "solar_center_lat": None, "solar_center_lng": None,
        "imagery_date": None,
        "roof_segment_data_available": False,
        "data_layers_available": False,
        "dsm_available": False,
        "mask_available": False,
        "error": None,
        "raw_building_insights_keys": [],
    }

    # 1) buildingInsights:findClosest
    bi_payload: Optional[dict] = None
    try:
        resp = requests.get(
            BUILDING_INSIGHTS_URL,
            params={
                "location.latitude": lat,
                "location.longitude": lng,
                "requiredQuality": "LOW",  # accept any quality so we maximize coverage
                "key": api_key,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            bi_payload = resp.json()
            out["solar_available"] = True
            out["building_insights_found"] = True
            out["raw_building_insights_keys"] = sorted(bi_payload.keys())[:20]
            ctr = bi_payload.get("center", {})
            out["solar_center_lat"] = ctr.get("latitude")
            out["solar_center_lng"] = ctr.get("longitude")
            out["imagery_date"] = (bi_payload.get("imageryDate") or {}).get("year")
            sp = bi_payload.get("solarPotential") or {}
            roof_segments = sp.get("roofSegmentStats") or []
            out["roof_segment_data_available"] = len(roof_segments) > 0
        elif resp.status_code == 404:
            out["error"] = "no_solar_coverage_at_location"
        elif resp.status_code == 403:
            out["error"] = f"403 Forbidden — Solar API likely not enabled on this key. {resp.text[:200]}"
        else:
            out["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        out["error"] = f"request failed: {e}"

    # 2) dataLayers:get — only attempt if buildingInsights succeeded
    if out["building_insights_found"]:
        try:
            dl_resp = requests.get(
                DATA_LAYERS_URL,
                params={
                    "location.latitude": lat,
                    "location.longitude": lng,
                    "radiusMeters": 50,
                    "view": "FULL_LAYERS",
                    "requiredQuality": "LOW",
                    "key": api_key,
                },
                timeout=20,
            )
            if dl_resp.status_code == 200:
                dl = dl_resp.json()
                out["data_layers_available"] = True
                out["dsm_available"] = bool(dl.get("dsmUrl"))
                out["mask_available"] = bool(dl.get("maskUrl"))
            else:
                # don't overwrite the higher-priority error from buildingInsights
                out.setdefault("data_layers_error", f"HTTP {dl_resp.status_code}: {dl_resp.text[:200]}")
        except Exception as e:
            out.setdefault("data_layers_error", f"request failed: {e}")

    if cache_path is not None:
        cache_path.write_text(json.dumps({
            "_schema_version": 1,
            "_created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": out,
        }, indent=2))

    return out


# ---------- Phase 4 Tier C: full measurement extractor ----------

SQM_TO_SQFT = 10.7639


def fetch_solar_building_data(
    address: str,
    lat: float,
    lng: float,
    api_key: str,
    cache: Optional[Cache] = None,
    refresh: bool = False,
) -> dict:
    """Fetch buildingInsights and extract: roof area + per-segment pitches.

    Returns: {
      available: bool,
      whole_roof_area_sqft: float | None,    # slanted (true) roof area
      ground_area_sqft: float | None,        # projected footprint per Solar
      weighted_pitch_deg: float | None,      # area-weighted mean pitch
      weighted_pitch_multiplier: float | None,
      max_pitch_deg, min_pitch_deg,
      roof_segment_count: int,
      roof_center_lat, roof_center_lng,
      imagery_quality: str | None,
      error: str | None,
    }
    """
    cache_dir: Optional[Path] = None
    cache_path: Optional[Path] = None
    if cache is not None:
        cache_dir = cache.paths.root / "solar_building_data"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{_addr_hash(address)}.json"
        if not refresh and cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text())
                if payload.get("_schema_version") in (2, 3):
                    data = payload["data"]
                    # backfill missing field for old caches
                    data.setdefault("roof_segment_centers", [])
                    return data
            except Exception:
                pass

    out: dict[str, Any] = {
        "available": False,
        "whole_roof_area_sqft": None,
        "ground_area_sqft": None,
        "weighted_pitch_deg": None,
        "weighted_pitch_multiplier": None,
        "max_pitch_deg": None,
        "min_pitch_deg": None,
        "roof_segment_count": 0,
        "roof_center_lat": None,
        "roof_center_lng": None,
        "roof_segment_centers": [],  # list of {lat, lng, area_sqft} for residual-uplift detection
        "imagery_quality": None,
        "error": None,
    }

    try:
        resp = requests.get(
            BUILDING_INSIGHTS_URL,
            params={
                "location.latitude": lat,
                "location.longitude": lng,
                "requiredQuality": "LOW",
                "key": api_key,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            out["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
        else:
            payload = resp.json()
            out["available"] = True
            out["imagery_quality"] = payload.get("imageryQuality")
            ctr = payload.get("center", {})
            out["roof_center_lat"] = ctr.get("latitude")
            out["roof_center_lng"] = ctr.get("longitude")
            sp = payload.get("solarPotential") or {}

            # Whole-roof slanted area
            whole = sp.get("wholeRoofStats") or {}
            wra = whole.get("areaMeters2")
            if wra is not None:
                out["whole_roof_area_sqft"] = round(float(wra) * SQM_TO_SQFT, 1)
            wga = whole.get("groundAreaMeters2")
            if wga is not None:
                out["ground_area_sqft"] = round(float(wga) * SQM_TO_SQFT, 1)

            # Per-segment pitches → area-weighted mean + segment centers
            segments = sp.get("roofSegmentStats") or []
            out["roof_segment_count"] = len(segments)
            if segments:
                import math
                pitch_areas: list[tuple[float, float]] = []
                centers: list[dict] = []
                for seg in segments:
                    pd = seg.get("pitchDegrees")
                    seg_area_m2 = (seg.get("stats") or {}).get("areaMeters2") or 0.0
                    if pd is not None:
                        pitch_areas.append((float(pd), float(seg_area_m2)))
                    ctr = seg.get("center") or {}
                    if ctr.get("latitude") is not None and ctr.get("longitude") is not None:
                        centers.append({
                            "lat": float(ctr["latitude"]),
                            "lng": float(ctr["longitude"]),
                            "area_sqft": round(float(seg_area_m2) * SQM_TO_SQFT, 1),
                        })
                out["roof_segment_centers"] = centers
                if pitch_areas:
                    total_w = sum(a for _, a in pitch_areas) or 1.0
                    weighted = sum(p * a for p, a in pitch_areas) / total_w
                    out["weighted_pitch_deg"] = round(weighted, 2)
                    out["weighted_pitch_multiplier"] = round(
                        1.0 / math.cos(math.radians(weighted)), 4
                    )
                    out["max_pitch_deg"] = round(max(p for p, _ in pitch_areas), 2)
                    out["min_pitch_deg"] = round(min(p for p, _ in pitch_areas), 2)
    except Exception as e:
        out["error"] = f"request failed: {e}"

    if cache_path is not None:
        cache_path.write_text(json.dumps({
            "_schema_version": 3,  # bumped — added roof_segment_centers
            "_created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": out,
        }, indent=2))

    return out
