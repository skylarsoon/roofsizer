"""Score Results vs benchmark records (dual reference or single real)."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ScoredResult:
    record: dict
    result: dict  # Result.to_dict()
    reference_type: str  # "dual_reference" | "single_real" | "none"
    reference_sqft_display: str
    pct_error: Optional[float] = None       # vs single_real
    pct_error_a: Optional[float] = None     # vs ref_a
    pct_error_b: Optional[float] = None     # vs ref_b
    error_avg: Optional[float] = None
    range_error_pct: Optional[float] = None
    in_range_5pct: Optional[bool] = None
    in_range_10pct: Optional[bool] = None
    under_or_over: Optional[str] = None
    failure_reason: Optional[str] = None


def _bucket(predicted: float, low: float, high: float) -> str:
    if predicted < low * 0.95:
        if predicted >= low * 0.80:
            return "under_5_20"
        if predicted >= low * 0.50:
            return "under_20_50"
        return "under_50_plus"
    if predicted > high * 1.05:
        if predicted <= high * 1.20:
            return "over_5_20"
        if predicted <= high * 1.50:
            return "over_20_50"
        return "over_50_plus"
    if low * 0.95 <= predicted <= high * 1.05:
        return "within_5pct"
    return "within_10pct"


def score_one(record: dict, result_dict: dict) -> ScoredResult:
    predicted = result_dict.get("predicted_sqft")

    if record.get("real_roof_sqft") not in (None, ""):
        ref = float(record["real_roof_sqft"])
        if predicted is None:
            return ScoredResult(
                record=record, result=result_dict,
                reference_type="single_real",
                reference_sqft_display=f"{ref:.0f}",
            )
        pct = abs(predicted - ref) / ref * 100.0
        bucket = _bucket(predicted, ref, ref)
        return ScoredResult(
            record=record, result=result_dict,
            reference_type="single_real",
            reference_sqft_display=f"{ref:.0f}",
            pct_error=round(pct, 2),
            error_avg=round(pct, 2),
            range_error_pct=round(pct, 2),
            in_range_5pct=pct <= 5.0,
            in_range_10pct=pct <= 10.0,
            under_or_over=bucket,
        )

    if record.get("ref_a_sqft") not in (None, "") and record.get("ref_b_sqft") not in (None, ""):
        ra = float(record["ref_a_sqft"])
        rb = float(record["ref_b_sqft"])
        low, high = min(ra, rb), max(ra, rb)
        if predicted is None:
            return ScoredResult(
                record=record, result=result_dict,
                reference_type="dual_reference",
                reference_sqft_display=f"{int(low)}–{int(high)}",
            )
        pct_a = abs(predicted - ra) / ra * 100.0
        pct_b = abs(predicted - rb) / rb * 100.0
        avg = (pct_a + pct_b) / 2.0
        if predicted > high:
            range_err = (predicted - high) / high * 100.0
        elif predicted < low:
            range_err = (low - predicted) / low * 100.0
        else:
            range_err = 0.0
        bucket = _bucket(predicted, low, high)
        return ScoredResult(
            record=record, result=result_dict,
            reference_type="dual_reference",
            reference_sqft_display=f"{int(low)}–{int(high)}",
            pct_error_a=round(pct_a, 2),
            pct_error_b=round(pct_b, 2),
            error_avg=round(avg, 2),
            range_error_pct=round(range_err, 2),
            in_range_5pct=(low * 0.95 <= predicted <= high * 1.05),
            in_range_10pct=(low * 0.90 <= predicted <= high * 1.10),
            under_or_over=bucket,
        )

    return ScoredResult(
        record=record, result=result_dict,
        reference_type="none",
        reference_sqft_display="",
    )


@dataclass
class ScenarioAggregate:
    dataset: str
    scenario: str
    scoreable_count: int = 0
    MAPE: Optional[float] = None
    median_absolute_pct_error: Optional[float] = None
    avg_range_error_pct: Optional[float] = None
    p90_error: Optional[float] = None
    worst_case_error: Optional[float] = None
    in_range_5_count: int = 0
    in_range_10_count: int = 0
    in_range_5_rate: Optional[float] = None
    in_range_10_rate: Optional[float] = None
    manual_review_count: int = 0


def aggregate(scoreds: list[ScoredResult], dataset: str, scenario: str) -> ScenarioAggregate:
    agg = ScenarioAggregate(dataset=dataset, scenario=scenario)
    errors = [s.error_avg for s in scoreds if s.error_avg is not None]
    range_errors = [s.range_error_pct for s in scoreds if s.range_error_pct is not None]

    agg.scoreable_count = len(errors)
    if errors:
        agg.MAPE = round(sum(errors) / len(errors), 2)
        agg.median_absolute_pct_error = round(statistics.median(errors), 2)
        agg.worst_case_error = round(max(errors), 2)
        if len(errors) > 1:
            sorted_e = sorted(errors)
            idx = max(0, int(round(0.9 * (len(sorted_e) - 1))))
            agg.p90_error = round(sorted_e[idx], 2)
        else:
            agg.p90_error = round(errors[0], 2)
    if range_errors:
        agg.avg_range_error_pct = round(sum(range_errors) / len(range_errors), 2)

    agg.in_range_5_count = sum(1 for s in scoreds if s.in_range_5pct)
    agg.in_range_10_count = sum(1 for s in scoreds if s.in_range_10pct)
    if agg.scoreable_count:
        agg.in_range_5_rate = round(agg.in_range_5_count / agg.scoreable_count, 3)
        agg.in_range_10_rate = round(agg.in_range_10_count / agg.scoreable_count, 3)
    agg.manual_review_count = sum(1 for s in scoreds if s.result.get("manual_review_needed"))
    return agg


def rank_scenarios(
    aggregates: list[ScenarioAggregate],
    rule: str,
    max_worst_case_error: float = 25.0,
) -> list[ScenarioAggregate]:
    """Rank scenarios. `rule` in {"calibration", "validation"}."""
    if not aggregates:
        return []
    eligible = [a for a in aggregates if a.scoreable_count > 0]
    if not eligible:
        return []

    soft_filtered = [a for a in eligible if (a.worst_case_error or 0) <= max_worst_case_error]
    pool = soft_filtered if soft_filtered else eligible

    if rule == "calibration":
        keyfn = lambda a: (
            a.avg_range_error_pct if a.avg_range_error_pct is not None else float("inf"),
            a.MAPE if a.MAPE is not None else float("inf"),
            a.worst_case_error if a.worst_case_error is not None else float("inf"),
        )
    elif rule == "validation":
        keyfn = lambda a: (
            a.MAPE if a.MAPE is not None else float("inf"),
            a.median_absolute_pct_error if a.median_absolute_pct_error is not None else float("inf"),
            a.p90_error if a.p90_error is not None else float("inf"),
            a.worst_case_error if a.worst_case_error is not None else float("inf"),
        )
    else:
        raise ValueError(f"unknown rule: {rule!r}")

    ranked = sorted(pool, key=keyfn)
    # any non-eligible (worst-case > threshold) fall to the end
    extras = [a for a in eligible if a not in ranked]
    return ranked + extras
