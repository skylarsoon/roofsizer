"""Per-property diagnosis with optional known-pitch decomposition for calibration."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .evaluate import ScoredResult
from .pitch import parse_pitch, pitch_to_multiplier


_FAIL_MESSAGES = {
    "under_5_20":  "UNDER 5–20% — likely missing/low pitch multiplier; try s2b or s3.",
    "under_20_50": "UNDER 20–50% — likely too-small footprint, missing attached garage, or wrong polygon; try s6 multi-building or SAM refine.",
    "under_50_plus": "UNDER >50% — selected polygon is wrong (shed/neighbor); manual review.",
    "over_5_20":   "OVER 5–20% — pitch too aggressive or neighbor partially included.",
    "over_20_50":  "OVER 20–50% — SAM mask grew into yard or driveway, or multi-building captured a neighbor.",
    "over_50_plus": "OVER >50% — wrong building entirely; manual review.",
    "within_5pct": "Within 5% of reference — looks correct.",
    "within_10pct": "Within 10% of reference — acceptable.",
}


def _decomposition(record: dict, scored: ScoredResult) -> Optional[dict]:
    """Decompose error into footprint vs pitch components when truth is available.

    Two truth sources:
    - Direct: validation_100 rich schema provides `truth_footprint_sqft` and
      `truth_pitch_multiplier` per record. We compare directly.
    - Implied: calibration records have `known_pitch` and dual references; we
      back-solve the implied true footprint from `ref_avg / true_pitch_multiplier`.
    """
    sel_area = scored.result.get("selected_polygon_area_sqft")
    pitch_mult = scored.result.get("pitch_multiplier")
    if sel_area is None or pitch_mult is None:
        return None

    # Direct truth (validation_100 rich schema)
    if record.get("truth_footprint_sqft") is not None and record.get("truth_pitch_multiplier") is not None:
        truth_fp = float(record["truth_footprint_sqft"])
        truth_mult = float(record["truth_pitch_multiplier"])
        truth_label = (
            f"{record.get('truth_pitch_deg', '?')}° "
            f"(complexity={record.get('roof_complexity', 'unknown')})"
        )
        source = "direct"
    elif record.get("known_pitch") not in (None, "") and record.get("ref_a_sqft") not in (None, "") and record.get("ref_b_sqft") not in (None, ""):
        rise, run = parse_pitch(record["known_pitch"])
        truth_mult = pitch_to_multiplier(rise, run)
        ra = float(record["ref_a_sqft"])
        rb = float(record["ref_b_sqft"])
        ref_avg = (ra + rb) / 2.0
        if truth_mult <= 0:
            return None
        truth_fp = ref_avg / truth_mult
        truth_label = record["known_pitch"]
        source = "implied"
    else:
        return None

    if truth_fp <= 0:
        return None
    footprint_error_pct = (sel_area - truth_fp) / truth_fp * 100.0
    pitch_ratio = pitch_mult / truth_mult
    abs_fp_err = abs(footprint_error_pct)
    abs_pitch_dev = abs(pitch_ratio - 1.0)
    if abs_fp_err < 5 and abs_pitch_dev < 0.05:
        interp = "Both pieces correct; remaining error is reference-spread noise."
    elif abs_fp_err > 10 and abs_pitch_dev < 0.05:
        interp = "Footprint problem (wrong polygon, missing garage, or stale MS data). Investigate building selection."
    elif abs_fp_err < 5 and abs_pitch_dev > 0.10:
        interp = "Pitch problem. Try s2b_calibration_mean_pitch or s3_llm_pitch."
    elif abs_fp_err > 10 and abs_pitch_dev > 0.10:
        interp = "Compounding problem (footprint AND pitch). Investigate building selection first."
    else:
        interp = "Mixed signals; either piece is within tolerance bands. No clear single fix."
    return {
        "truth_source": source,  # "direct" | "implied"
        "true_pitch_label": truth_label,
        "true_pitch_multiplier": round(truth_mult, 4),
        "implied_true_footprint": round(truth_fp, 1),
        "footprint_error_pct": round(footprint_error_pct, 2),
        "pitch_ratio": round(pitch_ratio, 4),
        "interpretation": interp,
    }


def write_diagnosis(scored: ScoredResult, out_path: Path) -> dict:
    record = scored.record
    res = scored.result
    out_path.parent.mkdir(parents=True, exist_ok=True)

    failure_reason = ""
    if scored.under_or_over and scored.under_or_over in _FAIL_MESSAGES:
        failure_reason = _FAIL_MESSAGES[scored.under_or_over]

    structural_warnings = list(res.get("warnings") or [])
    # Also recompute the same structural flags so the diagnosis file is self-contained.
    if (res.get("closest_polygon_distance_m") or 0) > 25:
        structural_warnings.append("closest_distance > 25m: MS footprint may be stale/missing")
    if res.get("polygon_count", 0) == 0:
        structural_warnings.append("no MS polygons returned; SAM/OSM fallback recommended")
    sel = res.get("selected_polygon_area_sqft")
    if sel is not None and (sel < 600 or sel > 8000):
        structural_warnings.append(f"selected area {sel} sqft is outside residential range (600–8000)")
    if (res.get("pitch_confidence") or 1.0) < 0.4 and res.get("pitch_source") == "llm":
        structural_warnings.append("pitch confidence < 0.4 (low)")
    structural_warnings = list(dict.fromkeys(structural_warnings))  # dedupe, keep order

    decomp = _decomposition(record, scored)

    lines = [
        f"# Diagnosis — {record.get('id', '?')} — {record.get('address', '')}",
        "",
        f"Scenario: `{res.get('scenario_id')}`",
        f"Run: `{res.get('run_id')}`",
        f"Predicted sqft: **{res.get('predicted_sqft')}**",
        f"Reference: {scored.reference_sqft_display} ({scored.reference_type})",
    ]
    if scored.error_avg is not None:
        lines.append(f"Error: {scored.error_avg}% (range_error: {scored.range_error_pct}%)")
    if scored.in_range_5pct is not None:
        lines.append(f"In range ±5%: {scored.in_range_5pct} | ±10%: {scored.in_range_10pct}")
    if scored.under_or_over:
        lines.append(f"Bucket: `{scored.under_or_over}`")
    if failure_reason:
        lines += ["", f"**Likely cause:** {failure_reason}"]
    lines += ["", "## Result fields", ""]
    for k in (
        "footprint_source", "selected_polygon_source", "selected_polygon_area_sqft",
        "footprint_sqft", "polygon_count", "closest_polygon_distance_m",
        "pitch_used", "pitch_multiplier", "pitch_source", "pitch_confidence",
        "image_provider", "zoom", "scale", "confidence", "manual_review_needed",
        "building_selection_reason",
    ):
        lines.append(f"- **{k}**: {res.get(k)}")
    if structural_warnings:
        lines += ["", "## Structural warnings"]
        lines += [f"- {w}" for w in structural_warnings]
    if decomp:
        lines += [
            "",
            "## Known-pitch decomposition",
            f"- **true_pitch**: {decomp['true_pitch_label']} (multiplier {decomp['true_pitch_multiplier']})",
            f"- **implied_true_footprint**: {decomp['implied_true_footprint']} sqft",
            f"- **footprint_error_pct**: {decomp['footprint_error_pct']}%",
            f"- **pitch_ratio**: {decomp['pitch_ratio']}",
            f"- **interpretation**: {decomp['interpretation']}",
        ]
    if res.get("candidates"):
        lines += ["", "## Top candidates"]
        for c in res["candidates"]:
            lines.append(f"- idx={c['index']:>3}  area={c['area_sqft']:>9.1f} sqft  dist={c['distance_m']:.2f} m")

    out_path.write_text("\n".join(lines) + "\n")
    return {"failure_reason": failure_reason, "decomposition": decomp}
