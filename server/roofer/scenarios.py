"""Scenario registry — Tier 1 only. Each scenario has a `pitch_method` callable
producing a PitchEstimate and a `footprint_method` (footprint source + selector).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .datasets import load_dataset
from .pitch import PitchEstimate, pitch_calibration_mean, pitch_default


@dataclass
class Scenario:
    id: str
    description: str
    tier: int
    pitch_method: Callable[[], PitchEstimate]   # returns a PitchEstimate to apply uniformly
    footprint_method: str = "microsoft_closest"  # symbolic; pipeline interprets
    selector: str = "closest"                     # "closest" | "residential" | "all_within"


def _pitch_none(**_) -> PitchEstimate:
    return PitchEstimate(rise=0.0, run=12.0, multiplier=1.0, source="none", confidence=0.0, label="flat")


def _pitch_six_twelve(**_) -> PitchEstimate:
    return pitch_default("6:12")


def _pitch_seven_seventy_five_twelve(**_) -> PitchEstimate:
    return pitch_default("7.75:12")


_calibration_mean_cache: Optional[PitchEstimate] = None


def _pitch_calibration_mean(**_) -> PitchEstimate:
    global _calibration_mean_cache
    if _calibration_mean_cache is None:
        cal = load_dataset("official_calibration_5", verbose=False)
        known = [r["known_pitch"] for r in cal if r.get("known_pitch")]
        _calibration_mean_cache = pitch_calibration_mean(known)
    return _calibration_mean_cache


def _pitch_llm(image_path=None, cfg=None, cache_root=None, **_) -> PitchEstimate:
    # Lazy import to keep Tier 1 free of OpenAI overhead until needed.
    from .data_sources.openai_vision import estimate_pitch_llm
    if image_path is None or cfg is None:
        return pitch_default("6:12")
    return estimate_pitch_llm(image_path=image_path, cfg=cfg, cache_root=cache_root)


def _pitch_llm_multi(image_paths=None, cfg=None, cache_root=None, **_) -> PitchEstimate:
    """Multi-image (3 zooms) + multi-shot (3 calls, median) vision pitch — OpenAI."""
    from .data_sources.openai_vision import estimate_pitch_llm_multi
    if not image_paths or cfg is None:
        return pitch_default("6:12")
    return estimate_pitch_llm_multi(
        image_paths=image_paths, cfg=cfg, cache_root=cache_root, n_shots=3,
    )


def _pitch_gemini_multi(image_paths=None, cfg=None, cache_root=None, **_) -> PitchEstimate:
    """Multi-image (3 zooms) + multi-shot (3 calls, median) vision pitch — Gemini Pro 3.1."""
    from .data_sources.gemini_vision import estimate_pitch_gemini_multi
    if not image_paths or cfg is None:
        return pitch_default("6:12")
    return estimate_pitch_gemini_multi(
        image_paths=image_paths, cfg=cfg, cache_root=cache_root, n_shots=3,
    )


def _pitch_regional(address=None, lat=None, **_) -> PitchEstimate:
    """Per-state / climate-region default pitch. No LLM call."""
    from .pitch import pitch_regional_default
    state = None
    if address:
        # Parse "..., NJ 07920" → "NJ"
        import re
        m = re.search(r",\s*([A-Z]{2})\s+\d{5}", address)
        if m:
            state = m.group(1)
    return pitch_regional_default(state=state, lat=lat)


def _pitch_llm_regional(image_path=None, cfg=None, cache_root=None, **_) -> PitchEstimate:
    """LLM classifies CLIMATE/STYLE region (vision can do this), then map → pitch.
    Single image, single shot. Cheap (1 LLM call per property)."""
    from .data_sources.openai_vision import estimate_pitch_via_regional_cue
    if image_path is None or cfg is None:
        return pitch_default("6:12")
    return estimate_pitch_via_regional_cue(image_path=image_path, cfg=cfg, cache_root=cache_root)


def _pitch_synthesizer(
    address=None, lat=None, lng=None,
    image_path=None, image_paths=None,
    cfg=None, cache=None, cache_root=None,
    artifact_dir=None,  # passed from pipeline so we can save dossier next to other artifacts
    _synth_ms_summary=None,
    _synth_osm_summary=None,
    **_,
) -> PitchEstimate:
    """Evidence-bundle synthesizer: gather 5 candidate pitches in PARALLEL plus
    raw context (Solar segments, MS/OSM polygons, Street View image), then a
    multimodal synthesizer LLM picks the final pitch from the full dossier.
    """
    from concurrent.futures import ThreadPoolExecutor
    from .data_sources.openai_vision import synthesize_pitch_from_dossier
    from pathlib import Path as _Path

    if image_path is None or cfg is None:
        return pitch_default("6:12")

    # ---- Pass 1: gather candidates in parallel ----
    def task_regional():
        return _pitch_regional(address=address, lat=lat)

    def task_llm_regional():
        return _pitch_llm_regional(image_path=image_path, cfg=cfg, cache_root=cache_root)

    def task_streetview():
        return _pitch_streetview(
            address=address, lat=lat, lng=lng,
            cfg=cfg, cache=cache, cache_root=cache_root,
        )

    def task_gpt_multi():
        if not image_paths:
            return pitch_default("6:12")
        return _pitch_llm_multi(image_paths=image_paths, cfg=cfg, cache_root=cache_root)

    def task_gemini_multi():
        if not image_paths:
            return pitch_default("6:12")
        return _pitch_gemini_multi(image_paths=image_paths, cfg=cfg, cache_root=cache_root)

    tasks = {
        "regional":      task_regional,
        "llm_regional":  task_llm_regional,
        "streetview":    task_streetview,
        "gpt_multi":     task_gpt_multi,
        "gemini_multi":  task_gemini_multi,
    }

    candidates: dict[str, Optional[PitchEstimate]] = {}
    raw_solar: dict = {}
    raw_streetview: dict = {}
    raw_osm: dict = {}

    def task_raw_solar():
        from .data_sources.google_solar import fetch_solar_building_data
        try:
            return fetch_solar_building_data(
                address=address, lat=lat, lng=lng,
                api_key=cfg.google_maps_api_key, cache=cache,
            )
        except Exception as e:
            return {"available": False, "error": str(e)[:200]}

    def task_raw_streetview():
        from .data_sources.google_streetview import fetch_streetview_coverage
        try:
            return fetch_streetview_coverage(
                address=address, lat=lat, lng=lng,
                api_key=cfg.google_maps_api_key, cache=cache,
            )
        except Exception as e:
            return {"streetview_available": False, "error": str(e)[:200]}

    def task_raw_osm():
        from .data_sources.osm_buildings import fetch_footprints as _osm_fetch
        from .geometry_utils import distance_to_point as _dist
        from .geometry_utils import polygon_area_sqft as _area_sqft
        try:
            r = _osm_fetch(address=address, lat=lat, lng=lng, buffer_meters=150, cache=cache)
            count = r.get("polygons_count", 0)
            if count == 0 or not r.get("polygons_geojson_path"):
                return {"count": 0, "closest_area_sqft": None, "closest_distance_m": None}
            import geopandas as gpd
            gdf = gpd.read_file(r["polygons_geojson_path"])
            if gdf.empty:
                return {"count": 0, "closest_area_sqft": None, "closest_distance_m": None}
            cands = sorted(
                ((_area_sqft(g, lat_hint=lat, lng_hint=lng), _dist(g, lat, lng))
                 for g in gdf.geometry),
                key=lambda x: x[1],
            )
            if not cands:
                return {"count": count, "closest_area_sqft": None, "closest_distance_m": None}
            top_area, top_dist = cands[0]
            return {"count": count,
                    "closest_area_sqft": round(top_area, 1),
                    "closest_distance_m": round(top_dist, 2)}
        except Exception as e:
            return {"count": 0, "error": str(e)[:200]}

    raw_tasks = {
        "solar": task_raw_solar,
        "streetview": task_raw_streetview,
        "osm": task_raw_osm,
    }

    with ThreadPoolExecutor(max_workers=8) as ex:
        candidate_futures = {ex.submit(fn): ("candidate", name) for name, fn in tasks.items()}
        raw_futures = {ex.submit(fn): ("raw", name) for name, fn in raw_tasks.items()}
        all_futures = {**candidate_futures, **raw_futures}
        for fut in all_futures:
            kind, name = all_futures[fut]
            try:
                result = fut.result()
            except Exception:
                result = None
            if kind == "candidate":
                candidates[name] = result
            elif kind == "raw":
                if name == "solar":
                    raw_solar = result or {}
                elif name == "streetview":
                    raw_streetview = result or {}
                elif name == "osm":
                    raw_osm = result or {}

    # Build raw_context from collected data + already-known MS/OSM (the pipeline's
    # _resolve_footprint computed those before calling the pitch method).
    raw_context = {
        "solar": raw_solar,
        "streetview": raw_streetview,
        "ms": _synth_ms_summary,
        "osm": _synth_osm_summary or raw_osm,  # prefer pipeline-provided summary; fall back to direct fetch
    }

    # Collect images: 3 zoom satellites + Street View
    all_image_paths = list(image_paths or [])
    sv_path = None
    try:
        from .data_sources.google_streetview import fetch_streetview_image
        sv_meta = fetch_streetview_image(
            address=address, lat=lat, lng=lng,
            api_key=cfg.google_maps_api_key, cache=cache,
        )
        if sv_meta.get("available") and sv_meta.get("path"):
            sv_path = sv_meta["path"]
            all_image_paths.append(str(sv_path))
            # Also drop into artifact_dir for the dossier
            if artifact_dir is not None:
                from shutil import copyfile
                target = _Path(artifact_dir) / "streetview.jpg"
                if not target.exists():
                    try:
                        copyfile(sv_path, target)
                    except Exception:
                        pass
    except Exception:
        pass

    # ---- Pass 2: synthesize ----
    final = synthesize_pitch_from_dossier(
        address=address,
        geocode={"lat": lat, "lng": lng},
        image_paths=all_image_paths,
        candidates=candidates,
        raw_context=raw_context,
        cfg=cfg, cache_root=cache_root,
        artifact_dir=_Path(artifact_dir) if artifact_dir else None,
    )

    # Append candidate breakdown to reasoning for audit
    parts = [f"{k}={v.rise:g}:12@{v.confidence:.2f}" for k, v in candidates.items() if v is not None]
    final.reasoning = (final.reasoning or "") + " | candidates: " + ", ".join(parts)
    return final


def _pitch_streetview(address=None, lat=None, lng=None, cfg=None, cache=None, cache_root=None, **_) -> PitchEstimate:
    """Fetch a Street View image and ask the LLM to read pitch from the side view.
    Falls back to regional default pitch if Street View unavailable."""
    from .data_sources.google_streetview import fetch_streetview_image
    from .data_sources.openai_vision import estimate_pitch_from_streetview
    from .pitch import pitch_regional_default
    import re as _re

    if address is None or cfg is None or lat is None or lng is None:
        return pitch_default("6:12")

    sv = fetch_streetview_image(
        address=address, lat=lat, lng=lng,
        api_key=cfg.google_maps_api_key, cache=cache,
    )
    if not sv.get("available") or not sv.get("path"):
        # Fall back to regional default
        state = None
        m = _re.search(r",\s*([A-Z]{2})\s+\d{5}", address)
        if m:
            state = m.group(1)
        fb = pitch_regional_default(state=state, lat=lat)
        fb.source = "streetview_fallback_regional"
        fb.reasoning = f"Street View unavailable: {sv.get('error', 'no image')}"
        return fb

    return estimate_pitch_from_streetview(
        image_path=sv["path"], cfg=cfg, cache_root=cache_root,
    )


def _pitch_solar(address=None, lat=None, lng=None, cfg=None, cache=None, **_) -> PitchEstimate:
    """Use Google Solar's per-segment pitches (area-weighted). Falls back to 6:12
    if the property isn't covered by Solar."""
    from .data_sources.google_solar import fetch_solar_building_data
    if address is None or cfg is None or lat is None or lng is None:
        return pitch_default("6:12")
    try:
        data = fetch_solar_building_data(address, lat, lng,
                                         api_key=cfg.google_maps_api_key,
                                         cache=cache)
    except Exception:
        return pitch_default("6:12")
    if not data.get("available") or data.get("weighted_pitch_multiplier") is None:
        return pitch_default("6:12")
    deg = data["weighted_pitch_deg"]
    mult = data["weighted_pitch_multiplier"]
    return PitchEstimate(
        rise=0.0, run=12.0, multiplier=mult,
        source="solar",
        confidence=0.85 if data.get("roof_segment_count", 0) >= 2 else 0.65,
        label=f"{deg:.1f}° (solar, {data.get('roof_segment_count', 0)} segs)",
    )


_REGISTRY: dict[str, Scenario] = {
    "s1_baseline": Scenario(
        id="s1_baseline",
        description="MS PC closest polygon, no pitch (lower bound)",
        tier=1,
        pitch_method=_pitch_none,
        footprint_method="microsoft_closest",
        selector="closest",
    ),
    "s2_default_pitch": Scenario(
        id="s2_default_pitch",
        description="MS PC closest polygon, fixed 6:12",
        tier=1,
        pitch_method=_pitch_six_twelve,
        footprint_method="microsoft_closest",
        selector="closest",
    ),
    "s2b_calibration_mean_pitch": Scenario(
        id="s2b_calibration_mean_pitch",
        description="MS PC closest polygon, mean of known calibration pitches",
        tier=1,
        pitch_method=_pitch_calibration_mean,
        footprint_method="microsoft_closest",
        selector="closest",
    ),
    "s2c_high_pitch_775": Scenario(
        id="s2c_high_pitch_775",
        description="MS PC closest polygon, fixed 7.75:12 (high pitch stress)",
        tier=1,
        pitch_method=_pitch_seven_seventy_five_twelve,
        footprint_method="microsoft_closest",
        selector="closest",
    ),
    "s3_llm_pitch": Scenario(
        id="s3_llm_pitch",
        description="MS PC closest polygon, OpenAI vision-derived per-property pitch",
        tier=2,
        pitch_method=_pitch_llm,
        footprint_method="microsoft_closest",
        selector="closest",
    ),
    "s6_multi_building": Scenario(
        id="s6_multi_building",
        description="MS PC, union of polygons within 25m AND area > 200 sqft, fixed 6:12",
        tier=3,
        pitch_method=_pitch_six_twelve,
        footprint_method="multi_building",
        selector="all_within",
    ),
    "s9_osm_fallback": Scenario(
        id="s9_osm_fallback",
        description="MS PC closest, OSM Overpass fallback if MS missing/far, fixed 6:12",
        tier=3,
        pitch_method=_pitch_six_twelve,
        footprint_method="osm_fallback",
        selector="residential",
    ),
    "s4_sam_default": Scenario(
        id="s4_sam_default",
        description="SAM 2 mask seeded by closest MS polygon centroid (or geocode), fixed 6:12",
        tier=3,
        pitch_method=_pitch_six_twelve,
        footprint_method="sam",
        selector="closest",
    ),
    "s_resilient_v1": Scenario(
        id="s_resilient_v1",
        description="Per-property: MS strict → multi-building → OSM → SAM → manual_review",
        tier=4,
        pitch_method=_pitch_six_twelve,
        footprint_method="resilient",
        selector="closest",
    ),
    # ---- Phase 4 scenarios ----
    "s8_solar_roof_area": Scenario(
        id="s8_solar_roof_area",
        description="Solar wholeRoofStats area directly (slanted roof area, no footprint or pitch math)",
        tier=4,
        pitch_method=_pitch_six_twelve,  # ignored — solar_direct doesn't multiply
        footprint_method="solar_direct",
        selector="closest",
    ),
    "s8b_solar_pitch_ms_footprint": Scenario(
        id="s8b_solar_pitch_ms_footprint",
        description="MS PC closest polygon × Solar weighted pitch",
        tier=4,
        pitch_method=_pitch_solar,
        footprint_method="microsoft_closest",
        selector="closest",
    ),
    "s9b_osm_wrong_building_guard": Scenario(
        id="s9b_osm_wrong_building_guard",
        description="MS unless suspicious (count=0, dist>25m, area∉[600,8000], or top-2 disagree); else OSM. 6:12.",
        tier=4,
        pitch_method=_pitch_six_twelve,
        footprint_method="osm_wrong_building_guard",
        selector="residential",
    ),
    "s4b_sam_strict_reject": Scenario(
        id="s4b_sam_strict_reject",
        description="SAM with stricter rejection: cov<25%, no edge-touch, ratio∈[0.5,1.5] vs MS",
        tier=4,
        pitch_method=_pitch_six_twelve,
        footprint_method="sam_strict",
        selector="closest",
    ),
    "s_resilient_v2": Scenario(
        id="s_resilient_v2",
        description="Solar pitch + Solar/MS/OSM footprint with strict gates → SAM strict → manual_review",
        tier=4,
        pitch_method=_pitch_solar,  # tries solar pitch; resilient_v2 footprint dispatches further
        footprint_method="resilient_v2",
        selector="closest",
    ),
    "s_resilient_v3": Scenario(
        id="s_resilient_v3",
        description="Solar (sane) → MS strict → OSM strict → manual_review. NO SAM.",
        tier=4,
        pitch_method=_pitch_six_twelve,  # only used if Solar branch doesn't fire
        footprint_method="resilient_v3",
        selector="closest",
    ),
    "s_resilient_v4": Scenario(
        id="s_resilient_v4",
        description="v3 + Solar residual-uplift: Solar adds nearby MS/OSM polygons it didn't cover (capped +30%).",
        tier=4,
        pitch_method=_pitch_six_twelve,
        footprint_method="resilient_v4",
        selector="closest",
    ),
    "s_solar_locate_default": Scenario(
        id="s_solar_locate_default",
        description="Solar gives building center → MS/OSM polygon at that center × fixed 6:12. Solar contributes coordinates only; all area math is ours.",
        tier=5,
        pitch_method=_pitch_six_twelve,
        footprint_method="solar_locate_ms",
        selector="closest",
    ),
    "s_solar_locate_llm_pitch": Scenario(
        id="s_solar_locate_llm_pitch",
        description="Solar gives building center → MS/OSM polygon at that center × LLM-vision pitch. Solar contributes coordinates only.",
        tier=5,
        pitch_method=_pitch_llm,
        footprint_method="solar_locate_ms",
        selector="closest",
    ),
    "s_llm_pitch_multi": Scenario(
        id="s_llm_pitch_multi",
        description="MS PC closest polygon × multi-image (3 zooms) + multi-shot (3 calls, median) vision pitch. Pure build, GPT-5.5.",
        tier=5,
        pitch_method=_pitch_llm_multi,
        footprint_method="microsoft_closest",
        selector="closest",
    ),
    "s_llm_pitch_multi_gemini": Scenario(
        id="s_llm_pitch_multi_gemini",
        description="MS PC closest polygon × multi-image (3 zooms) + multi-shot (3 calls, median) vision pitch. Pure build, Gemini 3.1 Pro.",
        tier=5,
        pitch_method=_pitch_gemini_multi,
        footprint_method="microsoft_closest",
        selector="closest",
    ),
    "s_regional_default_pitch": Scenario(
        id="s_regional_default_pitch",
        description="MS PC closest polygon × per-state / climate-region default pitch. NO LLM. Pure build.",
        tier=5,
        pitch_method=_pitch_regional,
        footprint_method="microsoft_closest",
        selector="closest",
    ),
    "s_solar_locate_regional": Scenario(
        id="s_solar_locate_regional",
        description="Solar coord disambiguates building → MS polygon × regional default pitch. NO LLM, no Solar measurement.",
        tier=5,
        pitch_method=_pitch_regional,
        footprint_method="solar_locate_ms",
        selector="closest",
    ),
    "s_llm_regional_pitch": Scenario(
        id="s_llm_regional_pitch",
        description="MS polygon × LLM-classified climate region → pitch. Asks LLM what it CAN see (vegetation, snow, style), not pitch directly.",
        tier=5,
        pitch_method=_pitch_llm_regional,
        footprint_method="microsoft_closest",
        selector="closest",
    ),
    "s_streetview_pitch": Scenario(
        id="s_streetview_pitch",
        description="MS polygon × Street View side-view LLM pitch (fallback regional default if Street View unavailable). Pitch IS visible from ground level.",
        tier=5,
        pitch_method=_pitch_streetview,
        footprint_method="microsoft_closest",
        selector="closest",
    ),
    "s_synthesizer": Scenario(
        id="s_synthesizer",
        description="MS polygon × SYNTHESIZER: 5 candidate pitches + raw Solar/MS/OSM/Street-View context → multimodal LLM synthesizer reads dossier (md + 4 images) and picks final pitch.",
        tier=6,
        pitch_method=_pitch_synthesizer,
        footprint_method="microsoft_closest",
        selector="closest",
    ),
}


def get_scenario(scenario_id: str) -> Scenario:
    if scenario_id not in _REGISTRY:
        raise KeyError(
            f"unknown scenario {scenario_id!r}. available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[scenario_id]


def list_scenarios(tier: Optional[int] = None) -> list[Scenario]:
    out = list(_REGISTRY.values())
    if tier is not None:
        out = [s for s in out if s.tier == tier]
    return out
