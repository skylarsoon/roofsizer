"""Aggregate failure patterns across a dataset run; write pattern_analysis.md."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .evaluate import ScoredResult


_BUCKET_GUIDANCE = {
    "under_5_20":    ("UNDER 5–20%", "pitch multiplier too low",
                      "compare s2_default_pitch vs s2b_calibration_mean_pitch; add s3_llm_pitch."),
    "under_20_50":   ("UNDER 20–50%", "too-small footprint, missing attached garage, or wrong polygon",
                      "test s6 multi-building selection; consider SAM refinement (Tier 3)."),
    "under_50_plus": ("UNDER >50%", "selected polygon is wrong (shed/neighbor)",
                      "tighten building selector; flag manual review."),
    "over_5_20":     ("OVER 5–20%", "pitch too aggressive or extra structure included",
                      "lower pitch default; review building selection radius."),
    "over_20_50":    ("OVER 20–50%", "neighbor or extra building included",
                      "tighten building selector or remove extra polygons."),
    "over_50_plus":  ("OVER >50%", "wrong building entirely",
                      "manual review; geocode may be off."),
}


def _bucket_examples(scoreds: list[ScoredResult], bucket: str, k: int = 3) -> list[str]:
    return [
        s.record.get("address", "?")
        for s in scoreds
        if s.under_or_over == bucket
    ][:k]


def _structural(scoreds: list[ScoredResult]) -> dict[str, list[ScoredResult]]:
    out: dict[str, list[ScoredResult]] = {
        "closest_distance_gt_25m": [],
        "polygon_count_zero": [],
        "selected_area_lt_600": [],
        "selected_area_gt_8000": [],
        "manual_review_needed": [],
    }
    for s in scoreds:
        r = s.result
        if (r.get("closest_polygon_distance_m") or 0) > 25:
            out["closest_distance_gt_25m"].append(s)
        if (r.get("polygon_count") or 0) == 0:
            out["polygon_count_zero"].append(s)
        sel = r.get("selected_polygon_area_sqft")
        if sel is not None and sel < 600:
            out["selected_area_lt_600"].append(s)
        if sel is not None and sel > 8000:
            out["selected_area_gt_8000"].append(s)
        if r.get("manual_review_needed"):
            out["manual_review_needed"].append(s)
    return out


def write_pattern_analysis(
    scoreds: list[ScoredResult],
    dataset: str,
    scenario: str,
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = len(scoreds)
    lines = [
        f"# Pattern analysis — {dataset} / {scenario}",
        "",
        f"Records analyzed: {n}",
    ]
    if n < 10:
        lines += [
            "",
            "> **Small sample — treat patterns as directional only.**",
        ]
    lines += [""]

    # Error buckets (only meaningful when scoreable)
    scoreable = [s for s in scoreds if s.error_avg is not None]
    if scoreable:
        lines += ["## Error patterns"]
        for bucket, (label, cause, recommend) in _BUCKET_GUIDANCE.items():
            members = [s for s in scoreable if s.under_or_over == bucket]
            if not members:
                continue
            pct = round(100 * len(members) / len(scoreable), 1)
            ex = _bucket_examples(scoreable, bucket)
            lines += [
                "",
                f"### Pattern: {label}",
                f"Count: {len(members)} / {len(scoreable)} ({pct}%)",
                f"Likely cause: {cause}",
                f"Recommended next experiment: {recommend}",
                "Examples:",
            ]
            lines += [f"- {a}" for a in ex]
        # within-range successes
        within5 = [s for s in scoreable if s.in_range_5pct]
        within10 = [s for s in scoreable if s.in_range_10pct]
        lines += [
            "",
            f"Within ±5%: {len(within5)} / {len(scoreable)}",
            f"Within ±10%: {len(within10)} / {len(scoreable)}",
        ]

    # Structural patterns
    struct = _structural(scoreds)
    if any(struct.values()):
        lines += ["", "## Structural patterns"]
        guidance = {
            "closest_distance_gt_25m": "MS footprint may be stale or geocode offset; consider OSM or SAM fallback.",
            "polygon_count_zero": "no MS polygons; needs SAM/OSM fallback.",
            "selected_area_lt_600": "selected polygon implausibly small; tighten selection rules.",
            "selected_area_gt_8000": "selected polygon implausibly large; check for merged neighbor or commercial structure.",
            "manual_review_needed": "low confidence — review before submission.",
        }
        for key, members in struct.items():
            if not members:
                continue
            pct = round(100 * len(members) / n, 1)
            ex = [s.record.get("address", "?") for s in members[:3]]
            lines += [
                "",
                f"### {key}",
                f"Count: {len(members)} / {n} ({pct}%)",
                f"Recommended: {guidance[key]}",
                "Examples:",
            ]
            lines += [f"- {a}" for a in ex]

    out_path.write_text("\n".join(lines) + "\n")
