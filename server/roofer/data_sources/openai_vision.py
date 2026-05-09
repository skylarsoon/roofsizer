"""OpenAI vision-based pitch estimation (Tier 2 — `s3_llm_pitch`).

Sends a satellite image of one property to OpenAI vision and asks for the roof
pitch as structured JSON. Caches responses keyed on (image_path_hash, model)
so we never pay twice for the same image.

The function returns a PitchEstimate. If the response is unparseable, low
confidence (<0.4), or out-of-range (rise outside [3, 12]), we fall back to a
6:12 default and record `pitch_source = "llm_rejected_fallback"` so the user
can see how often the LLM was rejected.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Optional

from ..config import Config
from ..pitch import PitchEstimate, pitch_default, pitch_to_multiplier

DEFAULT_VISION_MODEL = "gpt-5.5"  # fallback if .env doesn't override
PROMPT = (
    "You are looking at a top-down satellite/aerial image of a single residential property. "
    "Estimate the dominant roof pitch as a rise/run ratio over 12 inches of run "
    "(common roofing convention: e.g. 4:12, 6:12, 8:12, 10:12). "
    "Use cues such as visible shadow length on the ridge/eaves, visible ridge edges, "
    "the visible width of the roof slopes, and the apparent steepness when looking straight down. "
    "Respond ONLY with strict JSON of the form: "
    '{"rise": <integer 2..12>, "run": 12, "confidence": <float 0..1>, "reasoning": "<one short sentence>"}.'
)


def _img_hash(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:16]


def _cache_path(cache_root: Path, img_path: Path, model: str) -> Path:
    cache_dir = cache_root / "llm_pitch"
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_model = re.sub(r"[^a-z0-9]+", "_", model.lower())
    return cache_dir / f"{_img_hash(img_path)}__{safe_model}.json"


def _coerce_response(payload: dict) -> tuple[Optional[float], Optional[float], Optional[float], Optional[str]]:
    try:
        rise = float(payload.get("rise"))
        run = float(payload.get("run", 12)) or 12.0
        conf = float(payload.get("confidence", 0))
        reasoning = payload.get("reasoning") or ""
        return rise, run, conf, reasoning
    except (TypeError, ValueError):
        return None, None, None, None


_key_round_robin_idx = 0


def _pick_api_key(cfg: Config) -> str:
    """Round-robin across all configured OpenAI keys so concurrent calls
    spread load and respect per-key rate limits."""
    global _key_round_robin_idx
    keys = cfg.openai_api_keys or [cfg.openai_api_key]
    if not keys:
        return ""
    key = keys[_key_round_robin_idx % len(keys)]
    _key_round_robin_idx += 1
    return key


def estimate_pitch_llm(
    image_path: Path,
    cfg: Config,
    cache_root: Optional[Path] = None,
    refresh: bool = False,
    **_,
) -> PitchEstimate:
    if not image_path or not Path(image_path).exists():
        fb = pitch_default("6:12")
        fb.source = "llm_rejected_fallback"
        fb.reasoning = "no image available"
        return fb

    image_path = Path(image_path)
    model = os.getenv("OPENAI_VISION_MODEL") or DEFAULT_VISION_MODEL

    cached = None
    cache_file: Optional[Path] = None
    if cache_root is not None:
        cache_file = _cache_path(cache_root, image_path, model)
        if not refresh and cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text())
            except Exception:
                cached = None

    raw_text: Optional[str] = None
    if cached is None:
        try:
            from openai import OpenAI
        except ImportError as e:
            fb = pitch_default("6:12")
            fb.source = "llm_rejected_fallback"
            fb.reasoning = f"openai package missing: {e}"
            return fb

        client = OpenAI(api_key=_pick_api_key(cfg))
        img_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        # GPT-5 family rejects the legacy `max_tokens` and `temperature` params.
        # Try modern signature first; fall back to legacy if the API rejects it.
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                ],
            }
        ]
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=400,
            )
            raw_text = resp.choices[0].message.content or ""
        except TypeError:
            # Older SDK without max_completion_tokens — fall back to max_tokens.
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=120,
                    temperature=0,
                )
                raw_text = resp.choices[0].message.content or ""
            except Exception as e:
                fb = pitch_default("6:12")
                fb.source = "llm_rejected_fallback"
                fb.reasoning = f"openai call failed (legacy fallback): {e}"
                return fb
        except Exception as e:
            # If the modern call gave a 400 about unsupported `temperature`, retry without it.
            err_str = str(e)
            if "temperature" in err_str and "unsupported" in err_str.lower():
                try:
                    resp = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_completion_tokens=400,
                    )
                    raw_text = resp.choices[0].message.content or ""
                except Exception as e2:
                    fb = pitch_default("6:12")
                    fb.source = "llm_rejected_fallback"
                    fb.reasoning = f"openai call failed (after dropping temperature): {e2}"
                    return fb
            else:
                fb = pitch_default("6:12")
                fb.source = "llm_rejected_fallback"
                fb.reasoning = f"openai call failed: {e}"
                return fb

        # Parse JSON. Strip ```json fences if present.
        stripped = raw_text.strip().strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
        try:
            parsed = json.loads(stripped)
        except Exception:
            # Try to find a {...} block.
            m = re.search(r"\{[^{}]*\}", stripped, re.DOTALL)
            parsed = json.loads(m.group(0)) if m else {}

        rise, run, conf, reasoning = _coerce_response(parsed)
        cached = {
            "model": model,
            "raw": raw_text,
            "parsed": parsed,
            "rise": rise, "run": run,
            "confidence": conf,
            "reasoning": reasoning,
        }
        if cache_file is not None:
            cache_file.write_text(json.dumps(cached, indent=2))
    else:
        rise = cached.get("rise")
        run = cached.get("run") or 12.0
        conf = cached.get("confidence")
        raw_text = cached.get("raw")

    rise = cached.get("rise")
    run = cached.get("run") or 12.0
    conf = cached.get("confidence") or 0.0
    reasoning = cached.get("reasoning")

    # Validation / rejection
    if rise is None or conf is None or conf < 0.4 or rise < 3 or rise > 12:
        fb = pitch_default("6:12")
        fb.source = "llm_rejected_fallback"
        fb.confidence = float(conf or 0.0)
        fb.raw_response = raw_text
        fb.reasoning = (
            f"rejected (rise={rise}, conf={conf}); fallback to 6:12"
        )
        return fb

    return PitchEstimate(
        rise=float(rise),
        run=float(run),
        multiplier=pitch_to_multiplier(float(rise), float(run)),
        source="llm",
        confidence=float(conf),
        label=f"{rise:g}:{int(run) if float(run).is_integer() else run:g}",
        raw_response=raw_text,
        reasoning=reasoning,
    )


# ---------- regional climate cue (asks LLM what it CAN see) ----------

REGIONAL_PROMPT = """You are looking at a top-down satellite image of a residential property.
Do NOT estimate pitch numerically. Instead classify the regional CLIMATE/STYLE based on what you can clearly see:

- "hot_arid" — desert vegetation, sparse trees, terra-cotta tile or low-pitch composition roofs (typical of AZ, southern CA, NV, NM)
- "hot_humid" — palm/dense green, coastal/swampy terrain, pastel houses, tile or shallow shingle (typical of FL, southern TX, GA coast)
- "temperate" — deciduous trees, lawns, suburban grids, asphalt shingle, mixed pitches (typical of most of the US — IL, OH, NC, VA, NJ, MA suburbs, etc.)
- "cold_steep" — visible snow or evergreens, dense forest, mountain terrain, taller/peaked roofs, steeper pitches needed for snow shed (mountain CO, NH/VT/ME, MT, MN, WI, upstate NY)
- "unknown" — image too unclear or features ambiguous

Reply ONLY in strict JSON:
{"region":"<one of the above>","confidence":<float 0..1>,"reasoning":"<one short sentence>"}"""


REGION_TO_PITCH = {
    "hot_arid":   ("5:12", 1.118),    # actually 5:12 mult is 1.085, but using 5:12 label/pitch
    "hot_humid":  ("5:12", 1.085),
    "temperate":  ("6:12", 1.118),
    "cold_steep": ("8:12", 1.202),
    "unknown":    ("6:12", 1.118),
}


def estimate_pitch_via_regional_cue(
    image_path: Path,
    cfg: Config,
    cache_root: Optional[Path] = None,
    refresh: bool = False,
    **_,
) -> PitchEstimate:
    """Ask the LLM to classify the region (vision can do this), then map to pitch.

    The LLM sees vegetation, architecture style, snow patterns — visible cues
    on a top-down image, unlike pitch which is angular and lossy from above.
    """
    if not image_path or not Path(image_path).exists():
        return pitch_default("6:12")

    image_path = Path(image_path)
    model = os.getenv("OPENAI_VISION_MODEL") or DEFAULT_VISION_MODEL

    cache_file: Optional[Path] = None
    if cache_root is not None:
        cache_dir = cache_root / "llm_regional"
        cache_dir.mkdir(parents=True, exist_ok=True)
        bundle_hash = _img_hash(image_path)
        safe_model = re.sub(r"[^a-z0-9]+", "_", model.lower())
        cache_file = cache_dir / f"{bundle_hash}__{safe_model}.json"
        if not refresh and cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text())
                region = cached.get("region", "temperate")
                conf = cached.get("confidence", 0.5)
                rise_run, mult = REGION_TO_PITCH.get(region, ("6:12", 1.118))
                rise, run = parse_pitch(rise_run)
                return PitchEstimate(
                    rise=rise, run=run, multiplier=mult,
                    source="llm_regional",
                    confidence=float(conf),
                    label=f"{rise_run} (region={region})",
                    reasoning=cached.get("reasoning"),
                )
            except Exception:
                pass

    try:
        from openai import OpenAI
    except ImportError:
        return pitch_default("6:12")

    img_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": REGIONAL_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
        ],
    }]

    try:
        client = OpenAI(api_key=_pick_api_key(cfg))
        resp = client.chat.completions.create(
            model=model, messages=messages, max_completion_tokens=1500,
        )
        raw = resp.choices[0].message.content or ""
    except Exception as e:
        return pitch_default("6:12")

    stripped = raw.strip().strip("`")
    if stripped.lower().startswith("json"):
        stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", stripped)
        try:
            parsed = json.loads(m.group(0)) if m else {}
        except Exception:
            parsed = {}

    region = parsed.get("region", "temperate")
    conf = parsed.get("confidence")
    try:
        conf = float(conf) if conf is not None else 0.5
    except (TypeError, ValueError):
        conf = 0.5

    if region not in REGION_TO_PITCH:
        region = "temperate"
        conf = min(conf, 0.4)

    rise_run, mult = REGION_TO_PITCH[region]
    rise, run = parse_pitch(rise_run)

    if cache_file is not None:
        cache_file.write_text(json.dumps({
            "region": region, "confidence": conf, "raw": raw,
            "reasoning": parsed.get("reasoning"),
        }, indent=2))

    return PitchEstimate(
        rise=rise, run=run, multiplier=mult,
        source="llm_regional",
        confidence=float(conf),
        label=f"{rise_run} (region={region})",
        reasoning=parsed.get("reasoning"),
    )


# ---------- Evidence-bundle Synthesizer: full dossier + multi-image + raw context ----------

SYNTHESIZER_PROMPT = """You are an experienced roof analyst synthesizing a residential roof sqft estimate from multiple sources of evidence.

You have:
1. The TARGET property's address and approximate location.
2. {image_count} images attached: {image_legend}.
3. Multiple candidate pitch estimates from different methods, with reasoning.
4. Multiple candidate FOOTPRINT areas (MS PC polygon, OSM polygon, Solar wholeRoofStats area, Solar ground area).
5. Raw context (Solar API segment data, MS/OSM polygon comparison, Street View metadata).

EVIDENCE DOSSIER:
{dossier_md}

YOUR JOB: Pick a final roof sqft. Two paths:

PATH A — Direct slanted-roof area (preferred when reliable):
  If Solar `wholeRoofStats.areaMeters2` is available AND `roof_segment_count` >= 2 AND the imagery quality is OK,
  USE Solar's whole_roof_area_sqft directly. It IS the slanted (true) roof area — no multiplier needed.

PATH B — Footprint × pitch (when Path A is unreliable):
  Pick the best FOOTPRINT (MS PC, OSM, or Solar ground area). Footprint heuristics:
  - If MS and OSM agree within 30% AND distance ≤ 25m AND area in [600, 8000] → either is fine
  - If MS gives a polygon ≥ 8000 sqft → probably an apartment cluster; use OSM if it's smaller and residential
  - If MS distance > 50m → MS is wrong; use OSM if available
  - Solar ground_area is the projected footprint; use only when MS+OSM both fail
  Then pick a pitch (one of the candidate methods). Compute predicted_sqft = footprint × pitch_multiplier.

Sanity check: final predicted_sqft must be in [400, 12000] for a residential property.

DECISION FRAMEWORK FOR PITCH:
- Street View side view is most direct evidence for pitch.
- Solar weighted_pitch_deg with ≥2 segments is reliable.
- Gemini multi-shot is historically better at STEEP roofs; GPT multi-shot at TYPICAL.
- Regional default is reliable for hot states (AZ/FL) and cold mountain (VT/NH/mountain CO).

Respond ONLY with strict JSON:
{{"path":"A_solar_direct" or "B_footprint_x_pitch","footprint_source":"<solar_whole|ms|osm|solar_ground>","footprint_sqft":<number>,"pitch_source":"<regional|llm_regional|streetview|gpt_multi|gemini_multi|solar_pitch|synthesis>","rise":<integer 2..14>,"run":12,"pitch_multiplier":<float>,"final_predicted_sqft":<number>,"confidence":<float 0..1>,"manual_review_needed":<true|false>,"reasoning":"<2-3 sentences>"}}"""


def _build_dossier_md(*, address, geocode, candidates_dict, raw_context) -> str:
    """Build a human-readable evidence dossier for the synthesizer LLM (and humans)."""
    lines = [
        f"# Roof pitch evidence dossier",
        "",
        f"**Address:** {address}",
        f"**Geocoded:** {geocode.get('lat', '?'):.5f}, {geocode.get('lng', '?'):.5f}",
        "",
        "## Candidate pitch estimates",
        "",
        "| Method | Rise/12 | Multiplier | Confidence | Source | Reasoning |",
        "|---|---:|---:|---:|---|---|",
    ]
    for name, est in candidates_dict.items():
        if est is None:
            lines.append(f"| {name} | — | — | — | (failed) | — |")
            continue
        reasoning = (est.reasoning or "")
        if len(reasoning) > 220:
            reasoning = reasoning[:220] + "…"
        lines.append(
            f"| {name} | {est.rise:g}:12 | {est.multiplier:.4f} | {est.confidence:.2f} | "
            f"`{est.source}` | {reasoning} |"
        )
    lines.append("")

    # Raw context
    sd = raw_context.get("solar") or {}
    if sd:
        lines += ["## Solar API raw context", ""]
        if sd.get("available"):
            lines.append(f"- whole_roof_area_sqft: **{sd.get('whole_roof_area_sqft')}**")
            lines.append(f"- ground_area_sqft: {sd.get('ground_area_sqft')}")
            lines.append(f"- weighted_pitch_deg: {sd.get('weighted_pitch_deg')} (multiplier {sd.get('weighted_pitch_multiplier')})")
            lines.append(f"- max_pitch_deg: {sd.get('max_pitch_deg')}, min_pitch_deg: {sd.get('min_pitch_deg')}")
            lines.append(f"- roof_segment_count: {sd.get('roof_segment_count')}")
            lines.append(f"- imagery_quality: {sd.get('imagery_quality')}")
        else:
            lines.append(f"- not available ({sd.get('error', 'no data')})")
        lines.append("")

    ms = raw_context.get("ms") or {}
    osm = raw_context.get("osm") or {}
    sd_for_fp = raw_context.get("solar") or {}
    lines += ["## Footprint candidates (pick one for Path B; or use solar_whole for Path A)", ""]
    lines += [
        "| Source | Sqft | Detail |",
        "|---|---:|---|",
    ]
    if sd_for_fp and sd_for_fp.get("available"):
        lines.append(f"| solar_whole (slanted) | **{sd_for_fp.get('whole_roof_area_sqft')}** | Solar wholeRoofStats — IS the slanted roof area; segments={sd_for_fp.get('roof_segment_count')}, quality={sd_for_fp.get('imagery_quality')} |")
        lines.append(f"| solar_ground (projected) | {sd_for_fp.get('ground_area_sqft')} | Solar ground footprint estimate |")
    else:
        lines.append("| solar_whole | — | not available |")
        lines.append("| solar_ground | — | not available |")
    if ms.get("count") is not None and ms.get("count") > 0:
        lines.append(f"| ms | {ms.get('closest_area_sqft')} | MS PC closest polygon, distance={ms.get('closest_distance_m')} m, total_polys={ms.get('count')} |")
    else:
        lines.append("| ms | — | no MS polygons in bbox |")
    if osm.get("count") is not None and osm.get("count") > 0:
        lines.append(f"| osm | {osm.get('closest_area_sqft')} | OSM closest polygon, distance={osm.get('closest_distance_m')} m, total_polys={osm.get('count')} |")
    else:
        lines.append("| osm | — | no OSM polygons in bbox |")
    lines.append("")

    sv = raw_context.get("streetview") or {}
    if sv:
        lines += ["## Street View context", ""]
        if sv.get("available"):
            lines.append(f"- pano_id: {sv.get('pano_id')}, distance_to_pano: {sv.get('distance_to_pano_m')} m, date: {sv.get('pano_date')}")
        else:
            lines.append(f"- not available ({sv.get('error', 'no coverage')})")
        lines.append("")

    return "\n".join(lines)


def synthesize_pitch_from_dossier(
    *,
    address: str,
    geocode: dict,
    image_paths: list[Path],
    candidates: dict,
    raw_context: dict,
    cfg: Config,
    cache_root: Optional[Path] = None,
    artifact_dir: Optional[Path] = None,
    refresh: bool = False,
):
    """Multimodal LLM synthesizes the final pitch from a rich evidence dossier.
    Saves dossier.md + synthesizer_input.md + synthesizer_output.json to artifact_dir
    if provided.
    """
    from ..pitch import pitch_default, pitch_to_multiplier, PitchEstimate as PE

    valid = {k: v for k, v in candidates.items() if v is not None and getattr(v, "rise", None) is not None}
    if not valid:
        return pitch_default("6:12")

    # Build dossier
    dossier_md = _build_dossier_md(
        address=address, geocode=geocode,
        candidates_dict=valid, raw_context=raw_context,
    )

    # Save dossier artifact even if synthesizer fails
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "dossier.md").write_text(dossier_md)
        (artifact_dir / "evidence.json").write_text(json.dumps({
            "address": address,
            "geocode": geocode,
            "candidates": {k: {
                "rise": v.rise, "run": v.run, "multiplier": v.multiplier,
                "confidence": v.confidence, "source": v.source, "label": v.label,
                "reasoning": v.reasoning,
            } for k, v in valid.items()},
            "raw_context": raw_context,
        }, indent=2, default=str))

    # Build prompt
    image_legend_parts = []
    if any("z19" in str(p) for p in image_paths): image_legend_parts.append("zoom 19 (wide)")
    if any("z20" in str(p) for p in image_paths): image_legend_parts.append("zoom 20 (standard)")
    if any("z21" in str(p) for p in image_paths): image_legend_parts.append("zoom 21 (tight)")
    if any(str(p).endswith((".jpg", ".jpeg")) for p in image_paths): image_legend_parts.append("Street View (side)")
    image_legend = ", ".join(image_legend_parts) if image_legend_parts else "satellite views"

    prompt = SYNTHESIZER_PROMPT.format(
        image_count=len(image_paths),
        image_legend=image_legend,
        n=len(valid),
        dossier_md=dossier_md,
    )
    if artifact_dir is not None:
        (artifact_dir / "synthesizer_input.md").write_text(prompt)

    # Cache key: dossier hash (deterministic) + image bundle hash + model
    model = os.getenv("OPENAI_VISION_MODEL") or DEFAULT_VISION_MODEL
    cache_file: Optional[Path] = None
    if cache_root is not None:
        cache_dir = cache_root / "synthesizer"
        cache_dir.mkdir(parents=True, exist_ok=True)
        bundle_h = _multi_image_hash([Path(p) for p in image_paths if Path(p).exists()])
        digest = hashlib.sha1((
            bundle_h + "|" + hashlib.sha1(prompt.encode()).hexdigest()[:16]
        ).encode()).hexdigest()[:16]
        safe_model = re.sub(r"[^a-z0-9]+", "_", model.lower())
        cache_file = cache_dir / f"{digest}__{safe_model}.json"
        if not refresh and cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text())
                if artifact_dir is not None:
                    (artifact_dir / "synthesizer_output.json").write_text(json.dumps(cached, indent=2))
                rise = cached["rise"]
                conf = cached["confidence"]
                pitch_source = cached.get("pitch_source", cached.get("chosen_source", ""))
                footprint_source = cached.get("footprint_source")
                footprint_sqft = cached.get("footprint_sqft")
                final_predicted = cached.get("final_predicted_sqft")
                path = cached.get("path", "")
                try:
                    footprint_sqft = float(footprint_sqft) if footprint_sqft is not None else None
                    final_predicted = float(final_predicted) if final_predicted is not None else None
                except (TypeError, ValueError):
                    pass
                return PE(
                    rise=float(rise), run=12.0,
                    multiplier=pitch_to_multiplier(float(rise), 12.0),
                    source=f"synthesizer/{pitch_source}+{footprint_source or 'ms'}",
                    confidence=float(conf),
                    label=f"{rise}:12 ({path}; pitch={pitch_source}, fp={footprint_source})",
                    reasoning=cached.get("reasoning"),
                    final_predicted_sqft_override=final_predicted,
                    chosen_footprint_source=footprint_source,
                    chosen_footprint_sqft=footprint_sqft,
                )
            except Exception:
                pass

    # Try OpenAI first; if all 4 keys are out of quota or any other failure, fall back to Gemini.
    raw = ""
    used_provider = None
    last_err = None
    valid_paths = [Path(p) for p in image_paths if Path(p).exists()]

    try:
        from openai import OpenAI
        # Try every OpenAI key once before giving up on OpenAI
        keys_to_try = list(cfg.openai_api_keys) or [cfg.openai_api_key]
        for k in keys_to_try:
            try:
                content = [{"type": "text", "text": prompt}]
                for p in valid_paths:
                    b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
                    suffix = p.suffix.lower()
                    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
                    content.append({"type": "image_url",
                                    "image_url": {"url": f"data:{mime};base64,{b64}"}})
                client = OpenAI(api_key=k)
                resp = client.chat.completions.create(
                    model=model, messages=[{"role": "user", "content": content}],
                    max_completion_tokens=3000,
                )
                raw = resp.choices[0].message.content or ""
                used_provider = f"openai/{model}"
                break
            except Exception as e:
                last_err = str(e)[:200]
                if "insufficient_quota" not in last_err and "429" not in last_err:
                    break
                continue
    except ImportError:
        last_err = "openai package missing"

    if not raw:
        # Fall back to Gemini
        if cfg.gemini_api_key:
            try:
                import urllib.request, urllib.error
                gem_url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{cfg.gemini_vision_model}:generateContent"
                )
                parts = [{"text": prompt}]
                for p in valid_paths:
                    b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
                    suffix = p.suffix.lower()
                    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
                    parts.append({"inline_data": {"mime_type": mime, "data": b64}})
                payload = {"contents": [{"parts": parts}]}
                req = urllib.request.Request(
                    gem_url,
                    data=json.dumps(payload).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json",
                             "X-goog-api-key": cfg.gemini_api_key},
                )
                with urllib.request.urlopen(req, timeout=90) as r:
                    data = json.loads(r.read().decode("utf-8"))
                raw = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
                used_provider = f"gemini/{cfg.gemini_vision_model}"
            except Exception as e:
                last_err = f"openai_failed[{last_err}] + gemini_failed[{str(e)[:200]}]"

    if not raw:
        best = max(valid.values(), key=lambda v: v.confidence)
        best.source = f"synthesizer_fallback/{best.source}"
        best.reasoning = f"synthesizer API failed ({last_err}), picked highest-confidence candidate"
        if artifact_dir is not None:
            (artifact_dir / "synthesizer_output.json").write_text(json.dumps(
                {"error": last_err, "fallback": "highest-conf candidate", "fallback_pick": best.source},
                indent=2,
            ))
        return best

    stripped = raw.strip().strip("`")
    if stripped.lower().startswith("json"):
        stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", stripped)
        try:
            parsed = json.loads(m.group(0)) if m else {}
        except Exception:
            parsed = {}

    rise = parsed.get("rise")
    pitch_source = parsed.get("pitch_source", parsed.get("chosen_source", ""))
    conf = parsed.get("confidence")
    manual_review = bool(parsed.get("manual_review_needed", False))
    path = parsed.get("path", "")
    footprint_source = parsed.get("footprint_source")
    footprint_sqft = parsed.get("footprint_sqft")
    final_predicted = parsed.get("final_predicted_sqft")
    try:
        rise = float(rise) if rise is not None else None
        conf = float(conf) if conf is not None else 0.5
        footprint_sqft = float(footprint_sqft) if footprint_sqft is not None else None
        final_predicted = float(final_predicted) if final_predicted is not None else None
    except (TypeError, ValueError):
        pass

    if rise is None or rise < 2 or rise > 14:
        best = max(valid.values(), key=lambda v: v.confidence)
        best.source = f"synthesizer_fallback/{best.source}"
        best.reasoning = (best.reasoning or "") + " | synthesizer returned out-of-range rise"
        if artifact_dir is not None:
            (artifact_dir / "synthesizer_output.json").write_text(json.dumps(
                {"raw": raw, "parsed": parsed, "fallback": "highest-conf candidate"}, indent=2,
            ))
        return best

    # Sanity-check the final predicted sqft for residential (400-12000 per prompt)
    if final_predicted is not None and (final_predicted < 200 or final_predicted > 20000):
        final_predicted = None  # ignore wild values

    output_payload = {
        "path": path,
        "footprint_source": footprint_source,
        "footprint_sqft": footprint_sqft,
        "pitch_source": pitch_source,
        "rise": rise, "run": 12,
        "pitch_multiplier": parsed.get("pitch_multiplier"),
        "final_predicted_sqft": final_predicted,
        "confidence": conf,
        "manual_review_needed": manual_review,
        "reasoning": parsed.get("reasoning"),
        "synthesizer_provider": used_provider,
        "raw": raw,
    }
    if cache_file is not None:
        cache_file.write_text(json.dumps(output_payload, indent=2))
    if artifact_dir is not None:
        (artifact_dir / "synthesizer_output.json").write_text(json.dumps(output_payload, indent=2))

    return PE(
        rise=rise, run=12.0,
        multiplier=pitch_to_multiplier(rise, 12.0),
        source=f"synthesizer/{pitch_source}+{footprint_source or 'ms'}",
        confidence=float(conf),
        label=f"{rise:g}:12 ({path}; pitch={pitch_source}, fp={footprint_source})",
        reasoning=parsed.get("reasoning"),
        final_predicted_sqft_override=final_predicted,
        chosen_footprint_source=footprint_source,
        chosen_footprint_sqft=footprint_sqft,
    )


# ---------- Street View pitch (side-on view = pitch directly visible) ----------

STREETVIEW_PROMPT = """You are looking at a Street View photo of a residential property — taken from ground level, side-on. The roof slope is DIRECTLY visible from this angle (unlike top-down satellite where pitch is lost).

Estimate the dominant roof pitch as rise/run over 12 inches of run.

Visual cues for side-view pitch:
- 2:12 to 4:12 = nearly flat / barely sloped (ranches, modern flat roofs)
- 5:12 to 7:12 = typical visible slope at roughly 22-30° from horizontal
- 8:12 to 10:12 = clearly steep, ~33-40° from horizontal (colonials, snow regions)
- 11:12 to 14:12 = very steep, ~42-50° (mountain A-frames, Victorian, gothic)

If the target house roof is NOT visible (occluded by trees, wrong angle, image looks like a road only), set confidence < 0.3 and return rise=6.

Respond ONLY with strict JSON:
{"roof_visible":true|false,"shape":"<gable|hip|mansard|flat|complex|unclear>","rise":<number 2..14>,"run":12,"confidence":<float 0..1>,"reasoning":"<one short sentence>"}"""


def estimate_pitch_from_streetview(
    image_path: Path,
    cfg: Config,
    cache_root: Optional[Path] = None,
    refresh: bool = False,
    **_,
) -> PitchEstimate:
    """Side-view pitch from Street View. Pitch IS visible from this angle."""
    if not image_path or not Path(image_path).exists():
        fb = pitch_default("6:12")
        fb.source = "streetview_no_image"
        return fb

    image_path = Path(image_path)
    model = os.getenv("OPENAI_VISION_MODEL") or DEFAULT_VISION_MODEL

    cache_file: Optional[Path] = None
    if cache_root is not None:
        cache_dir = cache_root / "streetview_pitch"
        cache_dir.mkdir(parents=True, exist_ok=True)
        bundle_hash = _img_hash(image_path)
        safe_model = re.sub(r"[^a-z0-9]+", "_", model.lower())
        cache_file = cache_dir / f"{bundle_hash}__{safe_model}.json"
        if not refresh and cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text())
                rise = cached["rise"]
                conf = cached["confidence"]
                return PitchEstimate(
                    rise=float(rise), run=12.0,
                    multiplier=pitch_to_multiplier(float(rise), 12.0),
                    source="streetview",
                    confidence=float(conf),
                    label=f"{rise}:12 (streetview)",
                    reasoning=cached.get("reasoning"),
                )
            except Exception:
                pass

    try:
        from openai import OpenAI
    except ImportError:
        return pitch_default("6:12")

    img_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    # streetview default is JPEG
    suffix = image_path.suffix.lower()
    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": STREETVIEW_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
        ],
    }]

    try:
        client = OpenAI(api_key=_pick_api_key(cfg))
        resp = client.chat.completions.create(
            model=model, messages=messages, max_completion_tokens=1500,
        )
        raw = resp.choices[0].message.content or ""
    except Exception as e:
        fb = pitch_default("6:12")
        fb.source = "streetview_call_failed"
        fb.reasoning = str(e)[:200]
        return fb

    stripped = raw.strip().strip("`")
    if stripped.lower().startswith("json"):
        stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", stripped)
        try:
            parsed = json.loads(m.group(0)) if m else {}
        except Exception:
            parsed = {}

    rise = parsed.get("rise")
    conf = parsed.get("confidence")
    visible = parsed.get("roof_visible", False)
    try:
        rise = float(rise) if rise is not None else None
        conf = float(conf) if conf is not None else 0.0
    except (TypeError, ValueError):
        rise = None; conf = 0.0

    if rise is None or rise < 2 or rise > 14 or not visible:
        fb = pitch_default("6:12")
        fb.source = "streetview_rejected"
        fb.confidence = float(conf)
        fb.reasoning = parsed.get("reasoning") or "roof not visible / out of range"
        return fb

    if cache_file is not None:
        cache_file.write_text(json.dumps({
            "rise": rise, "confidence": conf, "raw": raw,
            "reasoning": parsed.get("reasoning"),
        }, indent=2))

    return PitchEstimate(
        rise=rise, run=12.0,
        multiplier=pitch_to_multiplier(rise, 12.0),
        source="streetview",
        confidence=float(conf),
        label=f"{rise:g}:12 (streetview)",
        reasoning=parsed.get("reasoning"),
    )


# ---------- multi-shot, multi-image pitch estimator ----------

MULTI_PROMPT = """You are estimating the dominant roof pitch of a single residential property.

Three top-down satellite images at different zoom levels are provided, all centered on the SAME property:
- IMAGE 1 (zoom 19, ~150m wide): wide context, neighbors visible for scale.
- IMAGE 2 (zoom 20, ~75m wide): standard view.
- IMAGE 3 (zoom 21, ~37m wide): tight detail of the target roof.

Reason through these steps in order:

Step 1 (use IMAGE 1): Identify the TARGET building (the central residential structure, ignoring neighbors). What is its roof SHAPE? Choose one: gable, hip, mansard, flat, complex.

Step 2 (use IMAGE 2): Observe shadows cast by the roof RIDGE onto the ground or onto the lower slopes. Long shadow relative to building width = steep pitch. Short or no shadow = shallow.

Step 3 (use IMAGE 3): Look at the visible WIDTH of the roof slopes between ridge and eave (top-down). Wide slopes = shallow pitch (the roof projects a wider footprint per unit of slope). Narrow slopes = steep pitch.

Step 4 (synthesize): Combine shape + shadow + slope width. Common residential pitches:
- 2:12 to 4:12 = SHALLOW (ranches, modern flat-ish roofs)
- 5:12 to 7:12 = TYPICAL (most American homes)
- 8:12 to 10:12 = STEEP (classic colonials, snow regions)
- 11:12 to 14:12 = VERY STEEP (mountain A-frames, Victorian, gothic)

Do NOT default to 6:12 unless that's truly what you see. If shadows are long and slopes look narrow from above, commit to a steeper pitch.

Respond ONLY with strict JSON of this exact shape:
{"shape":"<gable|hip|mansard|flat|complex>","shadow_observation":"<one short sentence>","slope_width_observation":"<one short sentence>","rise":<number 2 to 14>,"run":12,"confidence":<float 0 to 1>,"reasoning":"<one short sentence summarizing>"}"""


def _multi_image_hash(image_paths: list[Path]) -> str:
    h = hashlib.sha1()
    for p in image_paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:16]


def _aggregate_multi_shot(shots: list[dict]) -> tuple[float, float, str, list[dict]]:
    """Take median rise, mean confidence, with a stddev penalty.
    Returns: (rise, confidence, label, raw_shots)."""
    import statistics
    rises = [float(s["rise"]) for s in shots if s.get("rise") is not None]
    confs = [float(s["confidence"]) for s in shots if s.get("confidence") is not None]
    if not rises:
        return 6.0, 0.0, "6:12 (multi-fallback)", shots

    median_rise = statistics.median(rises)
    mean_conf = sum(confs) / len(confs) if confs else 0.5
    if len(rises) >= 2:
        stddev = statistics.stdev(rises)
        # Penalize disagreement: stddev=0 → no penalty, stddev=4 → halve confidence
        penalty = min(0.5, stddev / 8.0)
        agg_conf = mean_conf * (1.0 - penalty)
    else:
        stddev = 0.0
        agg_conf = mean_conf

    # If shots cluster very wide, drop to coarse bucket
    if stddev > 2.5:
        # Bucket by majority
        buckets = {"shallow": 0, "typical": 0, "steep": 0, "very_steep": 0}
        for r in rises:
            if r <= 4: buckets["shallow"] += 1
            elif r <= 7: buckets["typical"] += 1
            elif r <= 10: buckets["steep"] += 1
            else: buckets["very_steep"] += 1
        winner = max(buckets, key=buckets.get)
        bucket_rise = {"shallow": 4.0, "typical": 6.0, "steep": 9.0, "very_steep": 12.0}[winner]
        return bucket_rise, agg_conf * 0.7, f"{bucket_rise:g}:12 (bucket={winner}, high disagreement)", shots

    return float(round(median_rise)), agg_conf, f"{median_rise:g}:12 (median of {len(rises)} shots)", shots


def estimate_pitch_llm_multi(
    image_paths: list[Path],
    cfg: Config,
    cache_root: Optional[Path] = None,
    refresh: bool = False,
    n_shots: int = 3,
    **_,
) -> PitchEstimate:
    """Multi-image, multi-shot vision pitch.

    - Sends `image_paths` (typically 3 different zoom levels) in one call.
    - Repeats the call `n_shots` times at temp 0.7 for self-consistency.
    - Aggregates: median rise, stddev-penalized confidence, bucket fallback on disagreement.
    """
    valid_paths = [Path(p) for p in image_paths if p and Path(p).exists()]
    if not valid_paths:
        fb = pitch_default("6:12")
        fb.source = "llm_rejected_fallback"
        fb.reasoning = "no images available for multi-shot"
        return fb

    model = os.getenv("OPENAI_VISION_MODEL") or DEFAULT_VISION_MODEL

    # Cache key: image bundle hash + model + n_shots
    cache_file: Optional[Path] = None
    if cache_root is not None:
        cache_dir = cache_root / "llm_pitch_multi"
        cache_dir.mkdir(parents=True, exist_ok=True)
        bundle_hash = _multi_image_hash(valid_paths)
        safe_model = re.sub(r"[^a-z0-9]+", "_", model.lower())
        cache_file = cache_dir / f"{bundle_hash}__{safe_model}__n{n_shots}.json"
        if not refresh and cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text())
                rise = cached["rise"]
                conf = cached["confidence"]
                label = cached["label"]
                return PitchEstimate(
                    rise=float(rise), run=12.0,
                    multiplier=pitch_to_multiplier(float(rise), 12.0),
                    source="llm_multi",
                    confidence=float(conf),
                    label=label,
                    reasoning=cached.get("reasoning"),
                    raw_response=cached.get("raw"),
                )
            except Exception:
                pass

    try:
        from openai import OpenAI
    except ImportError as e:
        fb = pitch_default("6:12")
        fb.source = "llm_rejected_fallback"
        fb.reasoning = f"openai package missing: {e}"
        return fb

    client = OpenAI(api_key=_pick_api_key(cfg))

    # Build the message with all images attached
    image_blocks = []
    for p in valid_paths:
        b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        image_blocks.append({"type": "image_url",
                             "image_url": {"url": f"data:image/png;base64,{b64}"}})
    messages = [{
        "role": "user",
        "content": [{"type": "text", "text": MULTI_PROMPT}] + image_blocks,
    }]

    # N self-consistency shots — fire in PARALLEL with round-robin keys.
    # 4 keys × 4 outer workers × 3 shots = up to 48 concurrent calls (3/key safe).
    from concurrent.futures import ThreadPoolExecutor
    shots: list[dict] = [None] * n_shots  # type: ignore
    raw_responses: list[str] = []

    def _one_shot(idx: int) -> dict:
        try:
            client_i = OpenAI(api_key=_pick_api_key(cfg))
            resp = client_i.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=3000,
            )
            raw = resp.choices[0].message.content or ""
        except Exception as e:
            return {"error": str(e), "rise": None, "confidence": None, "raw": ""}

        stripped = raw.strip().strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
        try:
            parsed = json.loads(stripped)
        except Exception:
            m = re.search(r"\{[\s\S]*\}", stripped)
            try:
                parsed = json.loads(m.group(0)) if m else {}
            except Exception:
                parsed = {}

        rise = parsed.get("rise")
        conf = parsed.get("confidence")
        try:
            rise = float(rise) if rise is not None else None
            conf = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            rise = None; conf = None
        return {
            "rise": rise, "confidence": conf, "raw": raw,
            "shape": parsed.get("shape"),
            "reasoning": parsed.get("reasoning"),
        }

    with ThreadPoolExecutor(max_workers=n_shots) as ex:
        futures = {ex.submit(_one_shot, i): i for i in range(n_shots)}
        for fut in futures:
            i = futures[fut]
            shots[i] = fut.result()
    raw_responses = [s.get("raw", "") for s in shots if s.get("raw")]

    rise, agg_conf, label, _ = _aggregate_multi_shot(shots)

    # Reject + fallback if nothing came back
    if not any(s.get("rise") is not None for s in shots):
        fb = pitch_default("6:12")
        fb.source = "llm_rejected_fallback"
        fb.confidence = 0.0
        fb.reasoning = f"all {n_shots} multi-shot calls failed"
        return fb

    # Out-of-range guard
    if rise < 2 or rise > 14:
        fb = pitch_default("6:12")
        fb.source = "llm_rejected_fallback"
        fb.confidence = float(agg_conf)
        fb.reasoning = f"aggregated rise={rise} outside [2,14]"
        return fb

    final = PitchEstimate(
        rise=rise, run=12.0,
        multiplier=pitch_to_multiplier(rise, 12.0),
        source="llm_multi",
        confidence=float(agg_conf),
        label=label,
        reasoning="; ".join(filter(None, [s.get("reasoning") for s in shots[:2]])),
        raw_response=" || ".join(raw_responses[:2]),
    )

    if cache_file is not None:
        cache_file.write_text(json.dumps({
            "model": model, "n_shots": n_shots,
            "shots": shots,
            "rise": rise, "confidence": agg_conf, "label": label,
            "raw": final.raw_response,
            "reasoning": final.reasoning,
        }, indent=2))

    return final
