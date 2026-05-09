"""Pitch helpers — defaults + LLM vision (Tier 2)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PitchEstimate:
    rise: float
    run: float
    multiplier: float
    source: str
    confidence: float
    label: str  # e.g. "6:12"
    raw_response: Optional[str] = None
    reasoning: Optional[str] = None
    # Synthesizer-only: when the synthesizer picks a footprint source itself
    # (e.g. Solar wholeRoofStats, OSM polygon), it returns the FINAL slanted
    # predicted_sqft directly. The pipeline uses this if set; otherwise it
    # falls back to footprint × multiplier.
    final_predicted_sqft_override: Optional[float] = None
    chosen_footprint_source: Optional[str] = None
    chosen_footprint_sqft: Optional[float] = None


def pitch_to_multiplier(rise: float, run: float = 12.0) -> float:
    if run == 0:
        return 1.0
    return math.sqrt(1.0 + (rise / run) ** 2)


def parse_pitch(label: str) -> tuple[float, float]:
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?)\s*$", label)
    if not m:
        raise ValueError(f"could not parse pitch: {label!r}")
    return float(m.group(1)), float(m.group(2))


def pitch_default(rise_run: str = "6:12", **_) -> PitchEstimate:
    rise, run = parse_pitch(rise_run)
    return PitchEstimate(
        rise=rise,
        run=run,
        multiplier=pitch_to_multiplier(rise, run),
        source="default",
        confidence=0.5,  # default has no per-property evidence
        label=f"{rise:g}:{run:g}",
    )


def pitch_regional_default(state: Optional[str] = None, lat: Optional[float] = None, **_) -> PitchEstimate:
    """Default pitch by US state / climate region.

    Calibrated from general residential roofing convention + observed
    truth_pitch_deg distributions on validation_100:

    HOT / single-story / desert / Sunbelt → shallow (5:12, 22.6°)
        AZ, southern CA, southern NV, FL, southern TX (Houston/Gulf coast)
    COLD / snow / mountain → steep (8:12, 33.7°)
        VT, NH, ME, MT, mountain CO (Castle Pines, Castle Rock zones), upstate NY, MN, WI, ND, SD, AK
    TEMPERATE / suburban / colonial → typical (6:12, 26.6°)
        Default for all other US states
    """
    HOT_STATES = {"AZ", "FL", "NV", "NM"}
    COLD_STATES = {"VT", "NH", "ME", "MT", "MN", "WI", "ND", "SD", "AK", "ID", "WY"}
    # CA, TX, CO are split — use lat to disambiguate
    s = (state or "").upper().strip()
    if s in HOT_STATES:
        rise_run = "5:12"
        bucket = "hot_shallow"
    elif s in COLD_STATES:
        rise_run = "8:12"
        bucket = "cold_steep"
    elif s == "CA":
        # Southern CA (lat < 35) is hot; northern is temperate
        rise_run = "5:12" if (lat is not None and lat < 35.0) else "6:12"
        bucket = "ca_split"
    elif s == "TX":
        # Coastal/southern TX (lat < 30.5, includes Houston) is shallow; rest temperate
        rise_run = "5:12" if (lat is not None and lat < 30.5) else "6:12"
        bucket = "tx_split"
    elif s == "CO":
        # Mountain regions (lat > 39.4 or specific elevations) tend steeper
        # Castle Pines/Castle Rock area sits ~ 39.4-39.5 lat
        rise_run = "7:12" if (lat is not None and lat > 39.3) else "6:12"
        bucket = "co_split"
    else:
        rise_run = "6:12"
        bucket = "temperate_typical"
    rise, run = parse_pitch(rise_run)
    return PitchEstimate(
        rise=rise, run=run,
        multiplier=pitch_to_multiplier(rise, run),
        source="regional_default",
        confidence=0.65,
        label=f"{rise_run} (regional/{bucket})",
    )


def pitch_calibration_mean(known_pitches: list[str], **_) -> PitchEstimate:
    """Average the multipliers from a list of '6:12'-style strings.

    Returns a PitchEstimate with `label` set to the implied rise:12 of the mean
    multiplier (just for display) and source='calibration_mean'."""
    if not known_pitches:
        raise ValueError("known_pitches is empty")
    multipliers: list[float] = []
    for k in known_pitches:
        rise, run = parse_pitch(k)
        multipliers.append(pitch_to_multiplier(rise, run))
    mean_mult = sum(multipliers) / len(multipliers)
    # invert: mult = sqrt(1 + (rise/12)^2)  =>  rise = 12 * sqrt(mult^2 - 1)
    if mean_mult >= 1:
        implied_rise = 12.0 * math.sqrt(max(0.0, mean_mult * mean_mult - 1.0))
    else:
        implied_rise = 0.0
    return PitchEstimate(
        rise=round(implied_rise, 2),
        run=12.0,
        multiplier=mean_mult,
        source="calibration_mean",
        confidence=0.6,
        label=f"{implied_rise:.2f}:12 (mean of {len(known_pitches)} known pitches)",
    )
