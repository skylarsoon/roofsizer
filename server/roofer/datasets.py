"""Dataset loader supporting calibration, test, and validation_100."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_JSON = PROJECT_ROOT / "data" / "benchmarks.json"
VALIDATION_TEMPLATE = PROJECT_ROOT / "data" / "validation_100_template.csv"

# Search paths for validation_100 in priority order.
VALIDATION_CSV_CANDIDATES = [
    PROJECT_ROOT / "data" / "validation_100.csv",
    PROJECT_ROOT / "100" / "roof_sqft_sample.csv",
]

# Phase 4 curated discovery subset.
PHASE4_DISCOVERY_CSV = PROJECT_ROOT / "data" / "phase4_discovery_15.csv"

ALLOWED_SOURCE_QUALITY = {
    "commercial_report",
    "manual_measurement",
    "ml_estimate",
    "derived",
    "unknown",
}


def is_scoreable(record: dict) -> bool:
    if record.get("real_roof_sqft") not in (None, ""):
        return True
    return record.get("ref_a_sqft") not in (None, "") and record.get("ref_b_sqft") not in (None, "")


def _load_benchmarks_json() -> dict:
    if not BENCHMARKS_JSON.exists():
        raise FileNotFoundError(f"benchmarks file missing: {BENCHMARKS_JSON}")
    return json.loads(BENCHMARKS_JSON.read_text())


def _resolve_validation_csv() -> Optional[Path]:
    for candidate in VALIDATION_CSV_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _parse_float(raw: str) -> Optional[float]:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _compose_address(row: dict) -> str:
    """Combine split address parts (address, city, state, zip) into a single string,
    or fall back to the row's `address` field when the file is already flat."""
    addr = (row.get("address") or "").strip()
    city = (row.get("city") or "").strip()
    state = (row.get("state") or "").strip()
    zip_code = (row.get("zip") or row.get("zipcode") or "").strip()
    if city or state or zip_code:
        parts = [addr]
        if city:
            parts.append(city)
        tail = " ".join(p for p in (state, zip_code) if p)
        if tail:
            parts.append(tail)
        return ", ".join(p for p in parts if p)
    return addr


def _load_validation_100(verbose: bool = True) -> list[dict]:
    csv_path = _resolve_validation_csv()
    if csv_path is None:
        if verbose:
            print(
                f"validation_100 CSV not found in any of: "
                f"{[str(p) for p in VALIDATION_CSV_CANDIDATES]}. "
                f"See template at {VALIDATION_TEMPLATE}."
            )
        return []

    kept: list[dict] = []
    skipped_reasons: dict[str, int] = {}
    quality_breakdown: dict[str, int] = {q: 0 for q in ALLOWED_SOURCE_QUALITY}

    def skip(reason: str) -> None:
        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

    with csv_path.open() as f:
        reader = csv.DictReader(f)
        is_rich_schema = "footprint_sqft" in (reader.fieldnames or [])
        for row_num, row in enumerate(reader, start=2):  # 2 because header is row 1
            address = _compose_address(row)
            if not address:
                if verbose:
                    print(f"  validation_100 row {row_num}: skip — missing address")
                skip("missing_address")
                continue
            raw_sqft = row.get("real_roof_sqft", "")
            sqft = _parse_float(raw_sqft)
            if sqft is None:
                if verbose:
                    label = "non-numeric" if str(raw_sqft).strip() else "missing"
                    print(f"  validation_100 row {row_num}: skip — {label} real_roof_sqft={raw_sqft!r}")
                skip("missing_or_non_numeric_sqft")
                continue
            if sqft <= 0:
                if verbose:
                    print(f"  validation_100 row {row_num}: skip — real_roof_sqft <= 0 ({sqft})")
                skip("non_positive_sqft")
                continue
            if sqft < 300 or sqft > 15000:
                if verbose:
                    print(f"  validation_100 row {row_num}: WARN suspicious real_roof_sqft={sqft} (kept)")

            # Quality default: the rich schema (with footprint_sqft + pitch_multiplier) is
            # treated as 'manual_measurement' unless an explicit source_quality column is present.
            raw_quality = (row.get("source_quality") or "").strip()
            if raw_quality:
                quality = raw_quality
            elif is_rich_schema:
                quality = "manual_measurement"
            else:
                quality = "unknown"
            if quality not in ALLOWED_SOURCE_QUALITY:
                if verbose:
                    print(f"  validation_100 row {row_num}: WARN unknown source_quality={quality!r}, defaulting to 'unknown'")
                quality = "unknown"
            quality_breakdown[quality] += 1

            record = {
                "id": (row.get("id") or f"val_row{row_num:03d}").strip(),
                "address": address,
                "real_roof_sqft": sqft,
                "source": (row.get("source") or "").strip() or None,
                "source_quality": quality,
                "notes": (row.get("notes") or "").strip() or None,
                "dataset": "validation_100",
            }
            # Optional truth fields available in the rich schema:
            if is_rich_schema:
                record.update({
                    "truth_footprint_sqft": _parse_float(row.get("footprint_sqft")),
                    "truth_pitch_multiplier": _parse_float(row.get("pitch_multiplier_overall")),
                    "truth_pitch_deg": _parse_float(row.get("weighted_avg_pitch_deg")),
                    "roof_complexity": (row.get("roof_complexity") or "").strip() or None,
                    "num_mounting_planes": int(_parse_float(row.get("num_mounting_planes")) or 0) or None,
                    "roof_material_types": (row.get("roof_material_types") or "").strip() or None,
                })
            kept.append(record)

    if verbose:
        skipped_total = sum(skipped_reasons.values())
        reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(skipped_reasons.items())) or "none"
        breakdown_str = ", ".join(f"{k}={v}" for k, v in quality_breakdown.items())
        schema_note = " (rich schema: truth footprint+pitch available)" if is_rich_schema else ""
        print(
            f"validation_100: loaded from {csv_path}{schema_note}. "
            f"kept {len(kept)}, skipped {skipped_total} (reasons: {reasons_str}). "
            f"source_quality breakdown: {breakdown_str}."
        )
    return kept


def _load_phase4_discovery(verbose: bool = True) -> list[dict]:
    if not PHASE4_DISCOVERY_CSV.exists():
        if verbose:
            print(f"phase4_discovery_15 CSV not found at {PHASE4_DISCOVERY_CSV}.")
        return []
    kept: list[dict] = []
    with PHASE4_DISCOVERY_CSV.open() as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            address = _compose_address(row)
            if not address:
                if verbose:
                    print(f"  phase4 row {row_num}: skip — missing address")
                continue
            sqft = _parse_float(row.get("real_roof_sqft"))
            record = {
                "id": (row.get("id") or f"p4_row{row_num:03d}").strip(),
                "address": address,
                "real_roof_sqft": sqft,
                "truth_footprint_sqft": _parse_float(row.get("truth_footprint_sqft")),
                "truth_pitch_deg": _parse_float(row.get("truth_pitch")),
                "roof_complexity": (row.get("complexity") or "").strip() or None,
                "failure_bucket": (row.get("failure_bucket") or "").strip() or None,
                "source": (row.get("source") or "").strip() or None,
                "source_quality": (row.get("source_quality") or "manual_measurement").strip(),
                "notes": (row.get("notes") or "").strip() or None,
                "dataset": "phase4_discovery_15",
            }
            # truth_pitch_multiplier from degrees if available (sec(rad))
            import math
            if record["truth_pitch_deg"] is not None:
                record["truth_pitch_multiplier"] = round(
                    1.0 / math.cos(math.radians(record["truth_pitch_deg"])), 4
                )
            kept.append(record)
    if verbose:
        print(f"phase4_discovery_15: loaded {len(kept)} records from {PHASE4_DISCOVERY_CSV}.")
        bucket_counts: dict[str, int] = {}
        for r in kept:
            b = r.get("failure_bucket") or "(none)"
            bucket_counts[b] = bucket_counts.get(b, 0) + 1
        print(f"  failure_bucket breakdown: " + ", ".join(f"{k}={v}" for k, v in sorted(bucket_counts.items())))
    return kept


def load_dataset(name: str, verbose: bool = True) -> list[dict]:
    if name in {"calibration", "official_calibration_5"}:
        data = _load_benchmarks_json()
        return list(data["datasets"].get("official_calibration_5", []))
    if name in {"test", "official_test_5"}:
        data = _load_benchmarks_json()
        return list(data["datasets"].get("official_test_5", []))
    if name == "validation_100":
        return _load_validation_100(verbose=verbose)
    if name == "phase4_discovery_15":
        return _load_phase4_discovery(verbose=verbose)
    if name == "all_with_refs":
        cal = load_dataset("official_calibration_5", verbose=False)
        val = load_dataset("validation_100", verbose=verbose)
        return cal + val
    if name == "all":
        cal = load_dataset("official_calibration_5", verbose=False)
        test = load_dataset("official_test_5", verbose=False)
        val = load_dataset("validation_100", verbose=verbose)
        return cal + test + val
    raise ValueError(
        f"unknown dataset: {name!r}. expected one of: official_calibration_5, "
        f"official_test_5, validation_100, phase4_discovery_15, all_with_refs, all"
    )


def record_summary(record: dict) -> str:
    if record.get("real_roof_sqft") not in (None, ""):
        return f"real_roof_sqft={record['real_roof_sqft']}"
    if record.get("ref_a_sqft") not in (None, ""):
        return f"refs={record.get('ref_a_sqft')} / {record.get('ref_b_sqft')} (pitch {record.get('known_pitch')})"
    return "no references"
