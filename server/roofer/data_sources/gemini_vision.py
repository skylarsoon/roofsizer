"""Google Gemini vision-based pitch estimation — mirrors openai_vision.py.

Uses the same multi-image, multi-shot prompt as the OpenAI path, so the two
models can be compared head-to-head on identical inputs.

Important Gemini quirks (from GEMINI_INTEGRATION.md):
- gemini-3.1-pro-preview *requires* thinking mode — DO NOT pass `thinkingConfig.thinkingBudget=0`.
- Free tier rate limit: 25 RPM. Caller should throttle. We retry on 429 with retryDelay.
- Each call takes ~3 seconds (Pro 3.1 always thinks).
- Trust `data["modelVersion"]`, not the model's self-description.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from ..config import Config
from ..pitch import PitchEstimate, pitch_default, pitch_to_multiplier

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Same prompt as openai_vision.MULTI_PROMPT — apples to apples comparison.
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


def _post_with_retry(cfg: Config, payload: dict, max_retries: int = 3, timeout_s: int = 60) -> dict:
    """POST to Gemini. Retry on 429 honoring retryDelay; raise on other errors."""
    if not cfg.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    url = GEMINI_ENDPOINT.format(model=cfg.gemini_vision_model)
    body = json.dumps(payload).encode("utf-8")

    for attempt in range(max_retries + 1):
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-goog-api-key": cfg.gemini_api_key,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:1000]
            if e.code == 429 and attempt < max_retries:
                # Try to honor retryDelay if present in body
                wait = 8.0
                m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', err_body)
                if m:
                    try:
                        wait = float(m.group(1)) + 0.5
                    except Exception:
                        pass
                time.sleep(min(wait, 30.0))
                continue
            raise RuntimeError(f"Gemini HTTP {e.code}: {err_body[:300]}") from e
        except urllib.error.URLError as e:
            if attempt < max_retries:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise RuntimeError(f"Gemini URLError: {e}") from e
    raise RuntimeError("Gemini POST exhausted retries")


def _extract_text(data: dict) -> str:
    try:
        parts = data["candidates"][0]["content"]["parts"]
        # Gemini Pro 3.1 may return multiple parts; concat any with "text"
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        return ""


def _aggregate_multi_shot(shots: list[dict]) -> tuple[float, float, str]:
    rises = [float(s["rise"]) for s in shots if s.get("rise") is not None]
    confs = [float(s["confidence"]) for s in shots if s.get("confidence") is not None]
    if not rises:
        return 6.0, 0.0, "6:12 (multi-fallback)"
    median_rise = statistics.median(rises)
    mean_conf = sum(confs) / len(confs) if confs else 0.5
    if len(rises) >= 2:
        stddev = statistics.stdev(rises)
        penalty = min(0.5, stddev / 8.0)
        agg_conf = mean_conf * (1.0 - penalty)
    else:
        stddev = 0.0
        agg_conf = mean_conf

    if stddev > 2.5:
        buckets = {"shallow": 0, "typical": 0, "steep": 0, "very_steep": 0}
        for r in rises:
            if r <= 4: buckets["shallow"] += 1
            elif r <= 7: buckets["typical"] += 1
            elif r <= 10: buckets["steep"] += 1
            else: buckets["very_steep"] += 1
        winner = max(buckets, key=buckets.get)
        bucket_rise = {"shallow": 4.0, "typical": 6.0, "steep": 9.0, "very_steep": 12.0}[winner]
        return bucket_rise, agg_conf * 0.7, f"{bucket_rise:g}:12 (gemini bucket={winner}, high disagreement)"

    return float(round(median_rise)), agg_conf, f"{median_rise:g}:12 (gemini median of {len(rises)} shots)"


def estimate_pitch_gemini_multi(
    image_paths: list[Path],
    cfg: Config,
    cache_root: Optional[Path] = None,
    refresh: bool = False,
    n_shots: int = 3,
    **_,
) -> PitchEstimate:
    """Gemini-Pro-3.1 multi-image multi-shot pitch — same prompt as the OpenAI path."""
    valid_paths = [Path(p) for p in image_paths if p and Path(p).exists()]
    if not valid_paths:
        fb = pitch_default("6:12")
        fb.source = "gemini_rejected_fallback"
        fb.reasoning = "no images available for multi-shot"
        return fb

    if not cfg.gemini_api_key:
        fb = pitch_default("6:12")
        fb.source = "gemini_rejected_fallback"
        fb.reasoning = "GEMINI_API_KEY not set"
        return fb

    model = cfg.gemini_vision_model

    # Cache key: image bundle hash + model + n_shots
    cache_file: Optional[Path] = None
    if cache_root is not None:
        cache_dir = cache_root / "gemini_pitch_multi"
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
                    source="gemini_multi",
                    confidence=float(conf),
                    label=label,
                    reasoning=cached.get("reasoning"),
                    raw_response=cached.get("raw"),
                )
            except Exception:
                pass

    # Build content parts: one text + N images
    image_parts = []
    for p in valid_paths:
        b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        image_parts.append({"inline_data": {"mime_type": "image/png", "data": b64}})
    payload = {
        "contents": [{
            "parts": [{"text": MULTI_PROMPT}] + image_parts,
        }],
        # Note: do NOT set thinkingConfig — gemini-3.1-pro-preview rejects budget=0.
    }

    shots: list[dict] = []
    raw_responses: list[str] = []
    for i in range(n_shots):
        try:
            data = _post_with_retry(cfg, payload)
        except Exception as e:
            shots.append({"error": str(e)[:300], "rise": None, "confidence": None})
            continue

        raw = _extract_text(data)
        raw_responses.append(raw)

        stripped = (raw or "").strip().strip("`")
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
        shots.append({
            "rise": rise, "confidence": conf,
            "shape": parsed.get("shape"),
            "reasoning": parsed.get("reasoning"),
            "raw": raw,
            "model_version": data.get("modelVersion") if isinstance(data, dict) else None,
        })

    rise, agg_conf, label = _aggregate_multi_shot(shots)

    if not any(s.get("rise") is not None for s in shots):
        fb = pitch_default("6:12")
        fb.source = "gemini_rejected_fallback"
        fb.reasoning = f"all {n_shots} Gemini shots failed"
        return fb

    if rise < 2 or rise > 14:
        fb = pitch_default("6:12")
        fb.source = "gemini_rejected_fallback"
        fb.confidence = float(agg_conf)
        fb.reasoning = f"aggregated rise={rise} outside [2,14]"
        return fb

    final = PitchEstimate(
        rise=rise, run=12.0,
        multiplier=pitch_to_multiplier(rise, 12.0),
        source="gemini_multi",
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
