"""Pipeline orchestration: record + scenario -> Result + artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from .cache import Cache
from .config import Config
from .data_sources import (
    google_solar,
    google_static,
    microsoft_footprints,
    osm_buildings,
)
from .geocode import geocode_address
from .scenarios import Scenario
from .select_building import (
    Selection,
    pick_all_within,
    pick_closest,
    pick_residential,
    pick_residential_strict,
)


def address_slug(address: str) -> str:
    s = address.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:80]


@dataclass
class Result:
    run_id: str
    record_id: str
    address: str
    dataset: str
    scenario_id: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    footprint_source: Optional[str] = None
    selected_polygon_source: Optional[str] = None
    selected_polygon_area_sqft: Optional[float] = None
    footprint_sqft: Optional[float] = None
    polygon_count: int = 0
    closest_polygon_distance_m: Optional[float] = None
    pitch_used: Optional[str] = None
    pitch_multiplier: Optional[float] = None
    pitch_source: Optional[str] = None
    pitch_confidence: Optional[float] = None
    predicted_sqft: Optional[float] = None
    confidence: float = 1.0
    warnings: list[str] = field(default_factory=list)
    manual_review_needed: bool = False
    building_selection_reason: Optional[str] = None
    failure_reason: Optional[str] = None
    artifacts: dict[str, str] = field(default_factory=dict)
    candidates: list[dict] = field(default_factory=list)
    image_provider: Optional[str] = None
    zoom: Optional[int] = None
    scale: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "record_id": self.record_id,
            "address": self.address,
            "dataset": self.dataset,
            "scenario_id": self.scenario_id,
            "lat": self.lat,
            "lng": self.lng,
            "footprint_source": self.footprint_source,
            "selected_polygon_source": self.selected_polygon_source,
            "selected_polygon_area_sqft": self.selected_polygon_area_sqft,
            "footprint_sqft": self.footprint_sqft,
            "polygon_count": self.polygon_count,
            "closest_polygon_distance_m": self.closest_polygon_distance_m,
            "pitch_used": self.pitch_used,
            "pitch_multiplier": self.pitch_multiplier,
            "pitch_source": self.pitch_source,
            "pitch_confidence": self.pitch_confidence,
            "predicted_sqft": self.predicted_sqft,
            "confidence": self.confidence,
            "warnings": self.warnings,
            "manual_review_needed": self.manual_review_needed,
            "building_selection_reason": self.building_selection_reason,
            "failure_reason": self.failure_reason,
            "artifacts": self.artifacts,
            "candidates": self.candidates,
            "image_provider": self.image_provider,
            "zoom": self.zoom,
            "scale": self.scale,
        }


def _compute_confidence(result: Result, scenario: Scenario) -> None:
    score = 1.0
    # Source-specific calibration: Solar with residual uplift is our most accurate
    # path; pure Solar second; MS/OSM third. Don't penalize Solar predictions for
    # MS-side signals (they aren't using MS).
    if result.footprint_source == "solar":
        # Penalize if a residual uplift was triggered (means Solar missed a structure
        # → our patch is best-effort but not as solid as Solar agreeing with MS).
        if any("residual uplift" in w for w in result.warnings):
            score -= 0.10
        # Penalize if Solar/MS disagree by >2x — we're trusting Solar but the
        # mismatch increases regret risk.
        if any("Solar/MS disagreement" in w for w in result.warnings):
            score -= 0.20
        # Penalize when Solar is the only source (no MS, no OSM) — no cross-check.
        if result.polygon_count == 0:
            score -= 0.10
    elif result.footprint_source in ("microsoft", "osm"):
        # Standard MS/OSM penalties
        if result.closest_polygon_distance_m is not None and result.closest_polygon_distance_m > 25:
            score -= 0.30
            result.warnings.append("footprint may be stale/missing (closest > 25m)")
        if result.polygon_count == 0:
            score -= 0.25
        if result.selected_polygon_area_sqft is not None:
            if result.selected_polygon_area_sqft < 600 or result.selected_polygon_area_sqft > 8000:
                score -= 0.20
                result.warnings.append(
                    f"selected polygon outside residential range ({result.selected_polygon_area_sqft} sqft)"
                )
    elif result.footprint_source == "none":
        # manual_review path
        score = 0.0
    elif result.footprint_source == "sam":
        score -= 0.20  # SAM is rare in v3/v4 but log when used

    result.confidence = max(0.0, min(1.0, score))
    result.manual_review_needed = result.confidence < 0.6


def _select(selector_name: str, gdf: gpd.GeoDataFrame, lat: float, lng: float) -> Optional[Selection]:
    if selector_name == "closest":
        return pick_closest(gdf, lat, lng)
    if selector_name == "residential":
        return pick_residential(gdf, lat, lng)
    if selector_name == "residential_strict":
        return pick_residential_strict(gdf, lat, lng)
    if selector_name == "all_within":
        return pick_all_within(gdf, lat, lng)
    raise ValueError(f"unknown selector {selector_name!r}")


def _ms_polygon_quality_ok(gdf: gpd.GeoDataFrame, lat: float, lng: float,
                           max_distance_m: float = 25.0,
                           min_area_sqft: float = 600.0,
                           max_area_sqft: float = 8000.0) -> bool:
    """True if MS has at least one polygon that looks residential."""
    if gdf.empty:
        return False
    sel = pick_residential_strict(gdf, lat, lng,
                                  max_distance_m=max_distance_m,
                                  min_area_sqft=min_area_sqft,
                                  max_area_sqft=max_area_sqft)
    if sel is None:
        return False
    # If the strict picker fell back to "no polygon met" reason, treat as not-ok.
    return "falling back" not in sel.selection_reason


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    dlat = (lat2 - lat1) * 111320.0
    dlng = (lng2 - lng1) * 111320.0 * max(0.01, math.cos(math.radians((lat1 + lat2) / 2)))
    return math.hypot(dlat, dlng)


def _solar_residual_uplift(
    solar_data: dict,
    *,
    ms_gdf: gpd.GeoDataFrame,
    osm_gdf: Optional[gpd.GeoDataFrame],
    lat: float,
    lng: float,
) -> dict:
    """Detect MS/OSM polygons that look like structures Solar missed and
    compute the uplift in slanted sqft. Caps at +30% of base solar area.

    Returns: {
      base_solar_area, uplift_sqft, candidates_used, capped_at_30pct,
    }
    """
    from .geometry_utils import polygon_area_sqft as _area_sqft

    base = float(solar_data.get("whole_roof_area_sqft") or 0.0)
    pitch_mult = float(solar_data.get("weighted_pitch_multiplier") or 1.0)
    solar_centers = solar_data.get("roof_segment_centers") or []
    solar_center_lat = solar_data.get("roof_center_lat") or lat
    solar_center_lng = solar_data.get("roof_center_lng") or lng

    if base <= 0:
        return {"base_solar_area": base, "uplift_sqft": 0.0,
                "candidates_used": [], "capped_at_30pct": False}

    # A polygon is "Solar-covered" if its centroid is within 8m of any Solar segment center.
    OVERLAP_RADIUS_M = 8.0
    # Outer bound: 30m from Solar's roof center — beyond that, it's a different property.
    NEAR_RADIUS_M = 30.0
    # Min/max polygon area for residual structures (sqft).
    MIN_AREA_SQFT, MAX_AREA_SQFT = 200.0, 4000.0

    def is_covered_by_solar(centroid_lat: float, centroid_lng: float) -> bool:
        if not solar_centers:
            # No segment-level data — fall back to whole-roof center distance
            return _haversine_m(centroid_lat, centroid_lng,
                                solar_center_lat, solar_center_lng) <= OVERLAP_RADIUS_M
        return any(
            _haversine_m(centroid_lat, centroid_lng, c["lat"], c["lng"]) <= OVERLAP_RADIUS_M
            for c in solar_centers
        )

    # Collect candidates from MS + OSM
    candidates: list[dict] = []
    for source, gdf in [("ms", ms_gdf), ("osm", osm_gdf if osm_gdf is not None else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"))]:
        if gdf is None or gdf.empty:
            continue
        for idx, geom in enumerate(gdf.geometry):
            if geom is None or geom.is_empty:
                continue
            try:
                area_sqft = _area_sqft(geom, lat_hint=lat, lng_hint=lng)
            except Exception:
                continue
            if not (MIN_AREA_SQFT <= area_sqft <= MAX_AREA_SQFT):
                continue
            cx = geom.centroid.x  # lng
            cy = geom.centroid.y  # lat
            dist_to_solar_ctr = _haversine_m(cy, cx, solar_center_lat, solar_center_lng)
            if dist_to_solar_ctr > NEAR_RADIUS_M:
                continue  # different property
            if is_covered_by_solar(cy, cx):
                continue  # already in Solar's roof
            candidates.append({
                "source": source,
                "area_sqft": round(area_sqft, 1),
                "dist_m": round(dist_to_solar_ctr, 2),
                "centroid_lat": cy, "centroid_lng": cx,
            })

    # Deduplicate: MS and OSM often each have the same garage. Keep the larger
    # of two candidates whose centroids are within 5m of each other.
    candidates.sort(key=lambda c: -c["area_sqft"])
    kept: list[dict] = []
    for c in candidates:
        too_close = any(
            _haversine_m(c["centroid_lat"], c["centroid_lng"], k["centroid_lat"], k["centroid_lng"]) < 5.0
            for k in kept
        )
        if too_close:
            continue
        kept.append(c)

    # Compute uplift in slanted sqft (multiply ground area by Solar's pitch multiplier
    # — assume the missed structure has the same pitch as the main roof)
    raw_uplift = sum(c["area_sqft"] * pitch_mult for c in kept)
    cap = 0.30 * base
    uplift = min(raw_uplift, cap)
    return {
        "base_solar_area": base,
        "uplift_sqft": round(uplift, 1),
        "raw_uplift_sqft": round(raw_uplift, 1),
        "candidates_used": kept,
        "capped_at_30pct": raw_uplift > cap,
    }


def _sam_to_gdf(sam_meta: dict) -> gpd.GeoDataFrame:
    """Convert SAM data-source response to a single-row GeoDataFrame."""
    if not sam_meta or sam_meta.get("polygons_count", 0) == 0:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    geojson_path = sam_meta.get("polygons_geojson_path")
    if geojson_path is None or not Path(geojson_path).exists():
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return gpd.read_file(geojson_path)


def _resolve_footprint(
    scenario: Scenario,
    *,
    address: str,
    lat: float,
    lng: float,
    cfg: Config,
    cache: Cache,
    buffer_meters: int,
    ms_gdf: gpd.GeoDataFrame,
    ms_polygon_count: int,
    ms_closest_distance_m: Optional[float],
    artifact_dir: Path,
    res: "Result",
) -> tuple[gpd.GeoDataFrame, str, str]:
    """Decide which gdf to use and which selector to apply.
    Returns (gdf, selector_name, footprint_source_label)."""
    method = scenario.footprint_method

    if method in ("microsoft_closest", "microsoft_residential", "multi_building"):
        sel_map = {"microsoft_closest": "closest",
                   "microsoft_residential": "residential",
                   "multi_building": "all_within"}
        return ms_gdf, sel_map[method], "microsoft"

    if method == "osm_fallback":
        # Use MS if it looks decent; else fall back to OSM.
        if ms_polygon_count > 0 and ms_closest_distance_m is not None and ms_closest_distance_m <= 25:
            return ms_gdf, scenario.selector, "microsoft"
        # OSM
        osm_meta = osm_buildings.fetch_footprints(
            address=address, lat=lat, lng=lng,
            buffer_meters=buffer_meters, cache=cache,
        )
        if osm_meta.get("polygons_geojson_path") is not None:
            artifact_osm = artifact_dir / "osm_footprints.geojson"
            from shutil import copyfile
            if not artifact_osm.exists():
                copyfile(osm_meta["polygons_geojson_path"], artifact_osm)
            res.artifacts["osm_footprints_geojson"] = str(artifact_osm)
            osm_gdf = gpd.read_file(artifact_osm) if osm_meta["polygons_count"] > 0 else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        else:
            osm_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        if "error" in osm_meta.get("metadata", {}):
            res.warnings.append(f"osm fetch error: {osm_meta['metadata']['error']}")
        return osm_gdf, scenario.selector, "osm"

    if method == "sam":
        seed_polygon = None
        if ms_polygon_count > 0:
            sel = pick_closest(ms_gdf, lat, lng)
            if sel is not None:
                seed_polygon = sel.geometry
        sam_meta = {}
        try:
            from .data_sources.sam_mask import mask_building, SamUnavailable
            sam_meta = mask_building(
                address=address, lat=lat, lng=lng,
                image_path=Path(res.artifacts.get("satellite_path", "")) if res.artifacts.get("satellite_path") else Path(""),
                cfg=cfg, cache=cache,
                seed_polygon=seed_polygon,
                zoom=cfg.default_zoom, scale=cfg.default_scale,
            )
        except Exception as e:
            res.warnings.append(f"sam unavailable: {e}")
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), scenario.selector, "sam"
        if "error" in sam_meta.get("metadata", {}):
            res.warnings.append(f"sam error: {sam_meta['metadata']['error']}")
        if sam_meta.get("mask_png_path"):
            artifact_mask = artifact_dir / "sam_mask.png"
            from shutil import copyfile
            if not artifact_mask.exists():
                try:
                    copyfile(sam_meta["mask_png_path"], artifact_mask)
                    res.artifacts["sam_mask_path"] = str(artifact_mask)
                except Exception:
                    pass
        sam_gdf = _sam_to_gdf(sam_meta)
        return sam_gdf, "closest", "sam"

    if method == "solar_direct":
        # Use Solar wholeRoofStats area directly — return as a synthetic gdf
        # holding a tiny placeholder polygon at the geocoded point. Pipeline
        # will overwrite predicted_sqft directly.
        try:
            data = google_solar.fetch_solar_building_data(
                address=address, lat=lat, lng=lng,
                api_key=cfg.google_maps_api_key, cache=cache,
            )
        except Exception as e:
            res.warnings.append(f"solar fetch failed: {e}")
            data = {"available": False}
        if data.get("available") and data.get("whole_roof_area_sqft"):
            res._solar_data = data  # stash on result for pipeline to use
            from shapely.geometry import box as _shbox
            # Tiny placeholder polygon so the selection step succeeds
            placeholder = _shbox(lng - 1e-5, lat - 1e-5, lng + 1e-5, lat + 1e-5)
            sgdf = gpd.GeoDataFrame(geometry=[placeholder], crs="EPSG:4326")
            return sgdf, "closest", "solar"
        else:
            res.warnings.append(f"solar unavailable for direct area: {data.get('error', 'no data')}")
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), "closest", "solar"

    if method == "osm_wrong_building_guard":
        # MS unless suspicious. Suspicion signals:
        #  - polygon_count == 0
        #  - closest_distance > 25m
        #  - top polygon area outside [600, 8000] sqft
        #  - top-2 areas disagree by >40%
        ms_suspicious = False
        suspicion_reasons: list[str] = []
        if ms_polygon_count == 0:
            ms_suspicious = True; suspicion_reasons.append("polygon_count=0")
        if ms_closest_distance_m is not None and ms_closest_distance_m > 25:
            ms_suspicious = True; suspicion_reasons.append(f"closest>{ms_closest_distance_m:.0f}m")
        if not ms_gdf.empty:
            from .geometry_utils import polygon_area_sqft as _area_sqft
            from .geometry_utils import distance_to_point as _dist
            cands = sorted(
                [{"area": _area_sqft(g, lat_hint=lat, lng_hint=lng),
                  "dist": _dist(g, lat, lng)}
                 for g in ms_gdf.geometry],
                key=lambda c: c["dist"],
            )
            top_area = cands[0]["area"] if cands else 0
            if top_area > 0 and not (600 <= top_area <= 8000):
                ms_suspicious = True
                suspicion_reasons.append(f"top_area={top_area:.0f}∉[600,8000]")
            if len(cands) >= 2:
                a1, a2 = cands[0]["area"], cands[1]["area"]
                if a1 > 0 and abs(a1 - a2) / max(a1, a2) > 0.40:
                    ms_suspicious = True
                    suspicion_reasons.append(f"top2_diff={abs(a1-a2)/max(a1,a2):.0%}")

        if not ms_suspicious:
            return ms_gdf, "residential", "microsoft"

        res.warnings.append(f"ms_suspicious: {','.join(suspicion_reasons)} — falling back to OSM")
        osm_meta = osm_buildings.fetch_footprints(
            address=address, lat=lat, lng=lng,
            buffer_meters=buffer_meters, cache=cache,
        )
        osm_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        if osm_meta.get("polygons_geojson_path") is not None:
            artifact_osm = artifact_dir / "osm_footprints.geojson"
            from shutil import copyfile
            if not artifact_osm.exists():
                copyfile(osm_meta["polygons_geojson_path"], artifact_osm)
            res.artifacts["osm_footprints_geojson"] = str(artifact_osm)
            if osm_meta["polygons_count"] > 0:
                osm_gdf = gpd.read_file(artifact_osm)
        return osm_gdf, "residential", "osm"

    if method == "sam_strict":
        # SAM with strict rejection inside sam_mask.py (already cov<50%, edge handling).
        # Additional gate: if MS exists with a clean residential polygon,
        # reject SAM if its area is outside [0.5, 1.5] × MS area.
        seed_polygon = None
        ms_residential_area: Optional[float] = None
        if ms_polygon_count > 0:
            sel = pick_residential_strict(ms_gdf, lat, lng)
            if sel is not None and "falling back" not in sel.selection_reason:
                seed_polygon = sel.geometry
                ms_residential_area = sel.area_sqft
        try:
            from .data_sources.sam_mask import mask_building
            sam_meta = mask_building(
                address=address, lat=lat, lng=lng,
                image_path=Path(res.artifacts.get("satellite_path", "")) if res.artifacts.get("satellite_path") else Path(""),
                cfg=cfg, cache=cache,
                seed_polygon=seed_polygon,
                zoom=cfg.default_zoom, scale=cfg.default_scale,
            )
        except Exception as e:
            res.warnings.append(f"sam unavailable: {e}")
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), scenario.selector, "sam"
        if "error" in sam_meta.get("metadata", {}):
            res.warnings.append(f"sam error: {sam_meta['metadata']['error']}")
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), scenario.selector, "sam"
        if sam_meta.get("mask_png_path"):
            artifact_mask = artifact_dir / "sam_mask.png"
            from shutil import copyfile
            if not artifact_mask.exists():
                try:
                    copyfile(sam_meta["mask_png_path"], artifact_mask)
                    res.artifacts["sam_mask_path"] = str(artifact_mask)
                except Exception:
                    pass
        sam_gdf = _sam_to_gdf(sam_meta)
        if sam_gdf.empty:
            return sam_gdf, "closest", "sam"
        # Cross-validate against MS residential area
        if ms_residential_area:
            from .geometry_utils import polygon_area_sqft as _area_sqft
            sam_area = _area_sqft(sam_gdf.geometry.iloc[0], lat_hint=lat, lng_hint=lng)
            ratio = sam_area / max(ms_residential_area, 1.0)
            if ratio < 0.5 or ratio > 1.5:
                res.warnings.append(
                    f"sam_strict: rejecting SAM (sam={sam_area:.0f} sqft, ms={ms_residential_area:.0f} sqft, ratio={ratio:.2f})"
                )
                return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), "closest", "sam_rejected"
        return sam_gdf, "closest", "sam"

    if method == "solar_locate_ms":
        # Solar contributes only a (lat, lng) — the *correct* building's center.
        # We then pick the MS polygon closest to that Solar center, compute its
        # area ourselves (shapely + UTM), and let pitch come from whatever
        # pitch_method the scenario uses (LLM, default, etc.).
        target_lat, target_lng = lat, lng  # fallback
        offset_m = 0.0
        try:
            solar_data = google_solar.fetch_solar_building_data(
                address=address, lat=lat, lng=lng,
                api_key=cfg.google_maps_api_key, cache=cache,
            )
        except Exception as e:
            solar_data = {"available": False, "error": str(e)}
        if solar_data.get("available") and solar_data.get("roof_center_lat") is not None:
            target_lat = float(solar_data["roof_center_lat"])
            target_lng = float(solar_data["roof_center_lng"])
            offset_m = _haversine_m(lat, lng, target_lat, target_lng)
            res.warnings.append(
                f"solar_locate: Solar roof center {offset_m:.1f}m from geocoded point"
            )
        else:
            res.warnings.append(
                f"solar_locate: Solar unavailable ({solar_data.get('error', 'no data')}) — using geocoded point"
            )

        # Pick MS polygon closest to Solar center (or geocoded fallback).
        # Use pick_residential_strict so we still get the [600, 8000] sqft + 25m guard.
        if not ms_gdf.empty:
            sel = pick_residential_strict(ms_gdf, target_lat, target_lng)
            if sel is not None and "falling back" not in sel.selection_reason:
                # Wrap as a 1-row gdf so downstream selection is a no-op pick_closest
                chosen = gpd.GeoDataFrame(
                    [{"selected_via": "solar_center" if offset_m > 0 else "geocoded"}],
                    geometry=[sel.geometry], crs="EPSG:4326",
                )
                return chosen, "closest", "microsoft"
            # No qualifying polygon at Solar center either — try OSM fallback
        # OSM at Solar center
        osm_meta = osm_buildings.fetch_footprints(
            address=address, lat=lat, lng=lng,
            buffer_meters=buffer_meters, cache=cache,
        )
        if osm_meta.get("polygons_geojson_path") is not None and osm_meta["polygons_count"] > 0:
            osm_gdf = gpd.read_file(osm_meta["polygons_geojson_path"])
            sel = pick_residential_strict(osm_gdf, target_lat, target_lng)
            if sel is not None and "falling back" not in sel.selection_reason:
                chosen = gpd.GeoDataFrame(
                    [{"selected_via": "osm_at_solar_center" if offset_m > 0 else "osm_at_geocoded"}],
                    geometry=[sel.geometry], crs="EPSG:4326",
                )
                res.warnings.append("solar_locate: MS unavailable; using OSM at Solar center")
                return chosen, "closest", "osm"

        # Nothing usable — manual review
        res.warnings.append("solar_locate: no MS or OSM polygon found at target location")
        res.manual_review_needed = True
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), "closest", "none"

    if method == "resilient_v4":
        # Same as v3 but: when Solar fires, do a residual-uplift pass that
        # adds nearby MS/OSM polygons that aren't covered by Solar's roof
        # (capped at +30%).
        try:
            solar_data = google_solar.fetch_solar_building_data(
                address=address, lat=lat, lng=lng,
                api_key=cfg.google_maps_api_key, cache=cache,
            )
        except Exception as e:
            res.warnings.append(f"solar fetch failed: {e}")
            solar_data = {"available": False}

        ms_strict_sel: Optional[Selection] = None
        if not ms_gdf.empty:
            ms_strict_sel = pick_residential_strict(ms_gdf, lat, lng)
            if ms_strict_sel is not None and "falling back" in ms_strict_sel.selection_reason:
                ms_strict_sel = None

        # Pre-fetch OSM (we'll need it for residual uplift even if Solar fires)
        osm_meta = osm_buildings.fetch_footprints(
            address=address, lat=lat, lng=lng,
            buffer_meters=buffer_meters, cache=cache,
        )
        osm_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        if osm_meta.get("polygons_geojson_path") is not None:
            artifact_osm = artifact_dir / "osm_footprints.geojson"
            from shutil import copyfile
            if not artifact_osm.exists():
                copyfile(osm_meta["polygons_geojson_path"], artifact_osm)
            res.artifacts["osm_footprints_geojson"] = str(artifact_osm)
            if osm_meta["polygons_count"] > 0:
                osm_gdf = gpd.read_file(artifact_osm)

        solar_ok = False
        if solar_data.get("available") and solar_data.get("whole_roof_area_sqft"):
            solar_area = float(solar_data["whole_roof_area_sqft"])
            if not (600 <= solar_area <= 10000):
                res.warnings.append(
                    f"resilient_v4: Solar rejected (area {solar_area:.0f} ∉ [600, 10000])"
                )
            else:
                solar_ok = True
                if ms_strict_sel is not None:
                    ratio = solar_area / max(ms_strict_sel.area_sqft, 1.0)
                    if ratio < 0.5 or ratio > 2.0:
                        res.warnings.append(
                            f"resilient_v4: Solar/MS disagreement (solar={solar_area:.0f} vs "
                            f"ms_strict={ms_strict_sel.area_sqft:.0f}, ratio={ratio:.2f}) — trusting Solar"
                        )

        if solar_ok:
            # Compute residual uplift
            uplift_info = _solar_residual_uplift(
                solar_data, ms_gdf=ms_gdf, osm_gdf=osm_gdf, lat=lat, lng=lng,
            )
            adjusted = float(solar_data["whole_roof_area_sqft"]) + uplift_info["uplift_sqft"]
            # Stash for the pipeline-level predicted_sqft override
            adjusted_data = dict(solar_data)
            adjusted_data["whole_roof_area_sqft"] = adjusted
            res._solar_data = adjusted_data
            res._solar_residual_info = uplift_info
            if uplift_info["uplift_sqft"] > 0:
                cap_note = " (capped at 30%)" if uplift_info["capped_at_30pct"] else ""
                res.warnings.append(
                    f"resilient_v4: Solar+residual uplift {uplift_info['uplift_sqft']:.0f} sqft "
                    f"from {len(uplift_info['candidates_used'])} missed structure(s){cap_note}"
                )
                for c in uplift_info["candidates_used"]:
                    res.warnings.append(
                        f"  uplift candidate: {c['source']} area={c['area_sqft']:.0f} dist={c['dist_m']}m"
                    )
            res.warnings.append("resilient_v4: branch=solar_with_residual")
            from shapely.geometry import box as _shbox
            placeholder = _shbox(lng - 1e-5, lat - 1e-5, lng + 1e-5, lat + 1e-5)
            sgdf = gpd.GeoDataFrame(geometry=[placeholder], crs="EPSG:4326")
            return sgdf, "closest", "solar"

        # Solar not OK — same fallback as v3
        if ms_strict_sel is not None:
            res.warnings.append("resilient_v4: branch=ms_strict (solar unavailable/rejected)")
            return ms_gdf, "residential_strict", "microsoft"
        if not osm_gdf.empty:
            sel = pick_residential_strict(osm_gdf, lat, lng)
            if sel is not None and "falling back" not in sel.selection_reason:
                res.warnings.append("resilient_v4: branch=osm_strict")
                return osm_gdf, "residential_strict", "osm"
        res.warnings.append("resilient_v4: branch=manual_review")
        res.manual_review_needed = True
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), "closest", "none"

    if method == "resilient_v3":
        # Solar → MS → OSM → manual_review. NO SAM. Solar must pass sanity checks.
        # Sanity for Solar:
        #   1. whole_roof_area_sqft in [600, 10000]
        #   2. if MS strict residential available, |solar - ms_strict| / ms_strict < 0.5
        #      (block extreme disagreements like Solar finding a shed)

        # 1. Try Solar
        try:
            solar_data = google_solar.fetch_solar_building_data(
                address=address, lat=lat, lng=lng,
                api_key=cfg.google_maps_api_key, cache=cache,
            )
        except Exception as e:
            res.warnings.append(f"solar fetch failed: {e}")
            solar_data = {"available": False}

        # Compute MS strict reference area (used both as a sanity comparand
        # for Solar AND as fallback if Solar is rejected).
        ms_strict_sel: Optional[Selection] = None
        if not ms_gdf.empty:
            ms_strict_sel = pick_residential_strict(ms_gdf, lat, lng)
            if ms_strict_sel is not None and "falling back" in ms_strict_sel.selection_reason:
                ms_strict_sel = None

        solar_ok = False
        if solar_data.get("available") and solar_data.get("whole_roof_area_sqft"):
            solar_area = float(solar_data["whole_roof_area_sqft"])
            if not (600 <= solar_area <= 10000):
                res.warnings.append(
                    f"resilient_v3: Solar rejected (area {solar_area:.0f} ∉ [600, 10000])"
                )
            else:
                # Solar passed the absolute residential range. We TRUST Solar over
                # MS even when they disagree, because the common cause of large
                # disagreement is MS picking the wrong polygon (e.g. a garage or
                # apartment-cluster). Solar's roof boundary is more authoritative.
                # We log the disagreement but don't reject.
                solar_ok = True
                if ms_strict_sel is not None:
                    ratio = solar_area / max(ms_strict_sel.area_sqft, 1.0)
                    if ratio < 0.5 or ratio > 2.0:
                        res.warnings.append(
                            f"resilient_v3: Solar/MS disagreement (solar={solar_area:.0f} vs "
                            f"ms_strict={ms_strict_sel.area_sqft:.0f}, ratio={ratio:.2f}) — "
                            f"trusting Solar"
                        )

        if solar_ok:
            res.warnings.append("resilient_v3: branch=solar_direct")
            res._solar_data = solar_data
            from shapely.geometry import box as _shbox
            placeholder = _shbox(lng - 1e-5, lat - 1e-5, lng + 1e-5, lat + 1e-5)
            sgdf = gpd.GeoDataFrame(geometry=[placeholder], crs="EPSG:4326")
            return sgdf, "closest", "solar"

        # 2. Try MS strict residential
        if ms_strict_sel is not None:
            res.warnings.append("resilient_v3: branch=ms_strict")
            return ms_gdf, "residential_strict", "microsoft"

        # 3. Try OSM strict residential
        osm_meta = osm_buildings.fetch_footprints(
            address=address, lat=lat, lng=lng,
            buffer_meters=buffer_meters, cache=cache,
        )
        osm_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        if osm_meta.get("polygons_geojson_path") is not None:
            artifact_osm = artifact_dir / "osm_footprints.geojson"
            from shutil import copyfile
            if not artifact_osm.exists():
                copyfile(osm_meta["polygons_geojson_path"], artifact_osm)
            res.artifacts["osm_footprints_geojson"] = str(artifact_osm)
            if osm_meta["polygons_count"] > 0:
                osm_gdf = gpd.read_file(artifact_osm)
        if not osm_gdf.empty:
            sel = pick_residential_strict(osm_gdf, lat, lng)
            if sel is not None and "falling back" not in sel.selection_reason:
                res.warnings.append("resilient_v3: branch=osm_strict")
                return osm_gdf, "residential_strict", "osm"

        # 4. Manual review — NO SAM
        res.warnings.append("resilient_v3: branch=manual_review (Solar/MS/OSM all unavailable; SAM not used by v3)")
        res.manual_review_needed = True
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), "closest", "none"

    if method == "resilient_v2":
        # Try in order:
        # 1. MS strict residential
        # 2. OSM strict residential (if MS suspicious)
        # 3. Solar direct roof area (if MS+OSM both fail)
        # 4. SAM strict (last resort)
        # 5. manual review
        if _ms_polygon_quality_ok(ms_gdf, lat, lng):
            res.warnings.append("resilient_v2: branch=ms_strict")
            return ms_gdf, "residential_strict", "microsoft"

        # Try OSM
        osm_meta = osm_buildings.fetch_footprints(
            address=address, lat=lat, lng=lng,
            buffer_meters=buffer_meters, cache=cache,
        )
        osm_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        if osm_meta.get("polygons_geojson_path") is not None:
            artifact_osm = artifact_dir / "osm_footprints.geojson"
            from shutil import copyfile
            if not artifact_osm.exists():
                copyfile(osm_meta["polygons_geojson_path"], artifact_osm)
            res.artifacts["osm_footprints_geojson"] = str(artifact_osm)
            if osm_meta["polygons_count"] > 0:
                osm_gdf = gpd.read_file(artifact_osm)
        if not osm_gdf.empty:
            sel = pick_residential_strict(osm_gdf, lat, lng)
            if sel is not None and "falling back" not in sel.selection_reason:
                res.warnings.append("resilient_v2: branch=osm_strict")
                return osm_gdf, "residential_strict", "osm"

        # Try Solar direct
        try:
            data = google_solar.fetch_solar_building_data(
                address=address, lat=lat, lng=lng,
                api_key=cfg.google_maps_api_key, cache=cache,
            )
        except Exception:
            data = {"available": False}
        if data.get("available") and data.get("whole_roof_area_sqft"):
            res.warnings.append("resilient_v2: branch=solar_direct")
            res._solar_data = data
            from shapely.geometry import box as _shbox
            placeholder = _shbox(lng - 1e-5, lat - 1e-5, lng + 1e-5, lat + 1e-5)
            sgdf = gpd.GeoDataFrame(geometry=[placeholder], crs="EPSG:4326")
            return sgdf, "closest", "solar"

        # SAM strict
        try:
            from .data_sources.sam_mask import mask_building
            sam_meta = mask_building(
                address=address, lat=lat, lng=lng,
                image_path=Path(res.artifacts.get("satellite_path", "")),
                cfg=cfg, cache=cache, seed_polygon=None,
                zoom=cfg.default_zoom, scale=cfg.default_scale,
            )
            if not sam_meta.get("metadata", {}).get("error"):
                if sam_meta.get("mask_png_path"):
                    artifact_mask = artifact_dir / "sam_mask.png"
                    from shutil import copyfile
                    if not artifact_mask.exists():
                        try:
                            copyfile(sam_meta["mask_png_path"], artifact_mask)
                            res.artifacts["sam_mask_path"] = str(artifact_mask)
                        except Exception:
                            pass
                sam_gdf = _sam_to_gdf(sam_meta)
                if not sam_gdf.empty:
                    res.warnings.append("resilient_v2: branch=sam")
                    return sam_gdf, "closest", "sam"
        except Exception as e:
            res.warnings.append(f"sam fallback failed: {e}")

        res.warnings.append("resilient_v2: branch=none — manual review")
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), "closest", "none"

    if method == "resilient":
        # 1. Strict MS residential
        if _ms_polygon_quality_ok(ms_gdf, lat, lng):
            res.warnings.append("resilient: branch=ms_strict")
            return ms_gdf, "residential_strict", "microsoft"
        # 2. Multi-building if MS has multiple within 25m totalling >800 sqft
        union_sel = pick_all_within(ms_gdf, lat, lng, radius_m=25.0, min_area_sqft=200.0)
        if union_sel is not None and union_sel.area_sqft >= 800.0:
            res.warnings.append("resilient: branch=multi_building")
            return ms_gdf, "all_within", "microsoft"
        # 3. OSM fallback
        osm_meta = osm_buildings.fetch_footprints(
            address=address, lat=lat, lng=lng,
            buffer_meters=buffer_meters, cache=cache,
        )
        osm_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        if osm_meta.get("polygons_geojson_path") is not None:
            artifact_osm = artifact_dir / "osm_footprints.geojson"
            from shutil import copyfile
            if not artifact_osm.exists():
                copyfile(osm_meta["polygons_geojson_path"], artifact_osm)
            res.artifacts["osm_footprints_geojson"] = str(artifact_osm)
            if osm_meta["polygons_count"] > 0:
                osm_gdf = gpd.read_file(artifact_osm)
        if not osm_gdf.empty:
            sel = pick_residential_strict(osm_gdf, lat, lng)
            if sel is not None and "falling back" not in sel.selection_reason:
                res.warnings.append("resilient: branch=osm")
                return osm_gdf, "residential_strict", "osm"
        # 4. SAM fallback
        try:
            from .data_sources.sam_mask import mask_building
            sam_meta = mask_building(
                address=address, lat=lat, lng=lng,
                image_path=Path(res.artifacts.get("satellite_path", "")),
                cfg=cfg, cache=cache, seed_polygon=None,
                zoom=cfg.default_zoom, scale=cfg.default_scale,
            )
            if sam_meta.get("mask_png_path"):
                artifact_mask = artifact_dir / "sam_mask.png"
                from shutil import copyfile
                if not artifact_mask.exists():
                    try:
                        copyfile(sam_meta["mask_png_path"], artifact_mask)
                        res.artifacts["sam_mask_path"] = str(artifact_mask)
                    except Exception:
                        pass
            sam_gdf = _sam_to_gdf(sam_meta)
            if not sam_gdf.empty:
                res.warnings.append("resilient: branch=sam")
                return sam_gdf, "closest", "sam"
        except Exception as e:
            res.warnings.append(f"sam fallback failed: {e}")
        # 5. Nothing worked
        res.warnings.append("resilient: branch=none — flagging manual review")
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), "closest", "none"

    raise ValueError(f"unknown footprint_method {method!r}")


def _save_geojson_subset(geom: BaseGeometry, path: Path, props: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame([props], geometry=[geom], crs="EPSG:4326")
    gdf.to_file(path, driver="GeoJSON")


def run_pipeline(
    record: dict,
    scenario: Scenario,
    cfg: Config,
    cache: Cache,
    output_dir: Path,
    run_id: str,
    buffer_meters: int = 150,
) -> Result:
    address = record["address"]
    slug = address_slug(address)
    artifact_dir = output_dir / scenario.id / slug
    artifact_dir.mkdir(parents=True, exist_ok=True)

    res = Result(
        run_id=run_id,
        record_id=record.get("id", slug),
        address=address,
        dataset=record.get("dataset", ""),
        scenario_id=scenario.id,
    )

    # ---- geocode ----
    geocode_data = cache.get_geocode(address)
    if geocode_data is None:
        try:
            geocode_data = geocode_address(address, cfg)
            cache.put_geocode(address, geocode_data)
        except Exception as e:
            res.warnings.append(f"geocode failed: {e}")
            res.failure_reason = "geocode_failed"
            (artifact_dir / "prediction.json").write_text(json.dumps(res.to_dict(), indent=2))
            return res
    res.lat = geocode_data["latitude"]
    res.lng = geocode_data["longitude"]

    # ---- imagery ----
    try:
        img_meta = google_static.fetch_satellite_image(
            address=address, lat=res.lat, lng=res.lng,
            cfg=cfg,
            zoom=cfg.default_zoom, scale=cfg.default_scale, size=cfg.default_image_size,
            cache=cache,
        )
        # copy to artifact dir for self-contained inspection
        sat_path = artifact_dir / "satellite.png"
        if not sat_path.exists():
            from .data_sources.google_static import copy_to
            copy_to(sat_path, img_meta["path"])
        res.artifacts["satellite_path"] = str(sat_path)
        res.image_provider = img_meta["image_provider"]
        res.zoom = img_meta["zoom"]
        res.scale = img_meta["scale"]
    except Exception as e:
        res.warnings.append(f"imagery failed: {e}")

    # ---- MS footprints (always fetched first; cached) ----
    fp_meta = microsoft_footprints.fetch_footprints(
        address=address, lat=res.lat, lng=res.lng,
        buffer_meters=buffer_meters, cache=cache,
    )
    ms_count = fp_meta["polygons_count"]
    res.polygon_count = ms_count  # may be overridden later by SAM/OSM
    if fp_meta.get("polygons_geojson_path") is not None:
        artifact_fp = artifact_dir / "footprints.geojson"
        if not artifact_fp.exists():
            from shutil import copyfile
            copyfile(fp_meta["polygons_geojson_path"], artifact_fp)
        res.artifacts["footprints_geojson"] = str(artifact_fp)
        ms_gdf = gpd.read_file(artifact_fp) if ms_count > 0 else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    else:
        ms_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    # closest distance (for routing decisions)
    ms_closest_distance_m: Optional[float] = None
    if not ms_gdf.empty:
        from .geometry_utils import distance_to_point
        dists = [distance_to_point(g, res.lat, res.lng) for g in ms_gdf.geometry]
        ms_closest_distance_m = min(dists) if dists else None

    # ---- footprint dispatcher (selects gdf + selector based on scenario.footprint_method) ----
    selected_gdf, selector_name, footprint_source = _resolve_footprint(
        scenario,
        address=address, lat=res.lat, lng=res.lng,
        cfg=cfg, cache=cache, buffer_meters=buffer_meters,
        ms_gdf=ms_gdf, ms_polygon_count=ms_count,
        ms_closest_distance_m=ms_closest_distance_m,
        artifact_dir=artifact_dir, res=res,
    )
    res.footprint_source = footprint_source
    if footprint_source == "osm":
        res.polygon_count = len(selected_gdf)
    elif footprint_source == "sam":
        res.polygon_count = len(selected_gdf)
    # if microsoft, leave res.polygon_count = ms_count (already set)

    # ---- selection ----
    selection: Optional[Selection] = None
    if not selected_gdf.empty:
        selection = _select(selector_name, selected_gdf, res.lat, res.lng)
    if selection is None:
        res.warnings.append("no building polygon could be selected")
        res.failure_reason = "no_polygon_selected"
        res.manual_review_needed = True
    else:
        res.selected_polygon_area_sqft = round(selection.area_sqft, 1)
        res.footprint_sqft = round(selection.area_sqft, 1)
        res.closest_polygon_distance_m = round(selection.distance_m, 2)
        res.building_selection_reason = selection.selection_reason
        res.candidates = selection.candidates
        res.selected_polygon_source = f"{footprint_source}/{selector_name}"
        # save the selected polygon
        sel_path = artifact_dir / "selected.geojson"
        _save_geojson_subset(
            selection.geometry, sel_path,
            {
                "scenario": scenario.id,
                "area_sqft": res.selected_polygon_area_sqft,
                "distance_m": res.closest_polygon_distance_m,
                "reason": selection.selection_reason,
                "source": footprint_source,
            },
        )
        res.artifacts["selected_geojson"] = str(sel_path)
        # top candidates from whichever gdf we selected from
        if selection.candidates:
            top_path = artifact_dir / "top_candidates.geojson"
            geoms = [selected_gdf.geometry.iloc[c["index"]] for c in selection.candidates]
            top_gdf = gpd.GeoDataFrame(selection.candidates, geometry=geoms, crs="EPSG:4326")
            top_gdf.to_file(top_path, driver="GeoJSON")
            res.artifacts["top_candidates_geojson"] = str(top_path)

    # ---- pitch ----
    # If the pitch method wants multi-zoom imagery, fetch the extra zoom levels
    # and pass them as image_paths.
    image_paths_for_pitch: list[str] = []
    if scenario.pitch_method.__name__ in ("_pitch_llm_multi", "_pitch_gemini_multi", "_pitch_synthesizer"):
        try:
            multi = google_static.fetch_satellite_image_multi(
                address=address, lat=res.lat, lng=res.lng,
                cfg=cfg, zooms=(19, 20, 21),
                scale=cfg.default_scale, size=cfg.default_image_size,
                cache=cache,
            )
            for m in multi:
                if m.get("path"):
                    image_paths_for_pitch.append(str(m["path"]))
                    # Save extra zoom artifacts so demos can compare
                    z = m["zoom"]
                    art = artifact_dir / f"satellite_z{z}.png"
                    if not art.exists():
                        from .data_sources.google_static import copy_to
                        try:
                            copy_to(art, m["path"])
                        except Exception:
                            pass
        except Exception as e:
            res.warnings.append(f"multi-zoom fetch failed: {e}")

    # Build a small MS/OSM summary for the synthesizer dossier (no extra fetches —
    # use what's already been computed during _resolve_footprint).
    _synth_ms_summary = None
    if not ms_gdf.empty:
        from .geometry_utils import distance_to_point as _dist
        from .geometry_utils import polygon_area_sqft as _area_sqft
        cands = sorted(
            ((_area_sqft(g, lat_hint=res.lat, lng_hint=res.lng), _dist(g, res.lat, res.lng))
             for g in ms_gdf.geometry),
            key=lambda x: x[1],
        )
        if cands:
            top_area, top_dist = cands[0]
            _synth_ms_summary = {
                "count": ms_count,
                "closest_area_sqft": round(top_area, 1),
                "closest_distance_m": round(top_dist, 2),
            }
    _synth_osm_summary = None  # Pipeline doesn't always fetch OSM; synthesizer does its own raw fetch.

    pitch = scenario.pitch_method(
        address=address,
        image_path=res.artifacts.get("satellite_path"),
        image_paths=image_paths_for_pitch or None,
        cfg=cfg,
        lat=res.lat,
        lng=res.lng,
        cache=cache,
        cache_root=cache.paths.root,
        artifact_dir=str(artifact_dir),
        _synth_ms_summary=_synth_ms_summary,
        _synth_osm_summary=_synth_osm_summary,
    )
    res.pitch_used = pitch.label
    res.pitch_multiplier = round(pitch.multiplier, 4)
    res.pitch_source = pitch.source
    res.pitch_confidence = pitch.confidence
    if pitch.reasoning:
        res.warnings.append(f"pitch_reasoning: {pitch.reasoning}")

    # ---- predicted sqft ----
    solar_data = getattr(res, "_solar_data", None)
    if solar_data and solar_data.get("whole_roof_area_sqft") and footprint_source == "solar":
        # Solar wholeRoofStats area is the slanted (true) roof area — use it directly.
        res.predicted_sqft = round(float(solar_data["whole_roof_area_sqft"]), 1)
        res.footprint_sqft = solar_data.get("ground_area_sqft") or res.predicted_sqft
        res.pitch_used = (
            f"{solar_data.get('weighted_pitch_deg', '?')}° (solar direct area)"
            if solar_data.get("weighted_pitch_deg") is not None else "solar direct area"
        )
        res.pitch_multiplier = solar_data.get("weighted_pitch_multiplier") or 1.0
        res.pitch_source = "solar_direct"
        res.pitch_confidence = 0.85
        res.building_selection_reason = "solar wholeRoofStats area (slanted roof area)"
        res.selected_polygon_area_sqft = res.footprint_sqft
    elif getattr(pitch, "final_predicted_sqft_override", None) is not None:
        # Synthesizer picked footprint AND pitch — use its final number directly.
        res.predicted_sqft = round(float(pitch.final_predicted_sqft_override), 1)
        if pitch.chosen_footprint_sqft is not None:
            res.footprint_sqft = round(float(pitch.chosen_footprint_sqft), 1)
            res.selected_polygon_area_sqft = res.footprint_sqft
        if pitch.chosen_footprint_source:
            res.footprint_source = f"synthesizer:{pitch.chosen_footprint_source}"
            res.selected_polygon_source = pitch.chosen_footprint_source
    elif res.footprint_sqft is not None:
        res.predicted_sqft = round(res.footprint_sqft * pitch.multiplier, 1)

    # ---- confidence ----
    _compute_confidence(res, scenario)

    # ---- persist ----
    (artifact_dir / "prediction.json").write_text(json.dumps(res.to_dict(), indent=2))
    res.artifacts["dir"] = str(artifact_dir)

    return res
