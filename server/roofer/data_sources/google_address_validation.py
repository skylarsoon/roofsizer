"""Google Address Validation API — thin coverage probe (Phase 4 Tier A).

Validates an address and reports whether the validated geocode meaningfully
changes from our existing geocode. Actual re-routing of MS/OSM selection at
the new point lands in Phase 4 Tier C scenario `s_addr_validated_geocode`.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from ..cache import Cache, _addr_hash

VALIDATE_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat = (lat2 - lat1) * 111320.0
    dlng = (lng2 - lng1) * 111320.0 * max(0.01, math.cos(math.radians((lat1 + lat2) / 2)))
    return math.hypot(dlat, dlng)


def fetch_address_validation_coverage(
    address: str,
    api_key: str,
    original_lat: Optional[float] = None,
    original_lng: Optional[float] = None,
    cache: Optional[Cache] = None,
    refresh: bool = False,
) -> dict:
    """Probe Address Validation. Never raises.

    Returns: {
      original_address, validated_address,
      validation_verdict, has_unconfirmed_components, has_inferred_components,
      original_lat, original_lng,
      new_lat, new_lng,
      geocode_changed: bool,
      distance_old_new_m: float | None,
      component_changes: int,
      error: str | None,
    }
    """
    cache_dir: Optional[Path] = None
    cache_path: Optional[Path] = None
    if cache is not None:
        cache_dir = cache.paths.root / "address_validation"
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
        "original_address": address,
        "validated_address": None,
        "validation_verdict": None,
        "has_unconfirmed_components": None,
        "has_inferred_components": None,
        "original_lat": original_lat,
        "original_lng": original_lng,
        "new_lat": None,
        "new_lng": None,
        "geocode_changed": False,
        "distance_old_new_m": None,
        "component_changes": 0,
        "error": None,
    }

    try:
        resp = requests.post(
            VALIDATE_URL,
            params={"key": api_key},
            json={"address": {"addressLines": [address]}},
            timeout=15,
        )
        if resp.status_code == 200:
            j = resp.json()
            result = j.get("result") or {}
            address_obj = result.get("address") or {}
            out["validated_address"] = address_obj.get("formattedAddress")
            verdict = result.get("verdict") or {}
            input_granularity = verdict.get("inputGranularity")
            validation_granularity = verdict.get("validationGranularity")
            geocode_granularity = verdict.get("geocodeGranularity")
            out["validation_verdict"] = (
                f"input={input_granularity},validation={validation_granularity},geocode={geocode_granularity}"
            )
            out["has_unconfirmed_components"] = bool(verdict.get("hasUnconfirmedComponents"))
            out["has_inferred_components"] = bool(verdict.get("hasInferredComponents"))
            comps = address_obj.get("addressComponents") or []
            out["component_changes"] = sum(
                1 for c in comps
                if c.get("confirmationLevel") in {"UNCONFIRMED_BUT_PLAUSIBLE", "UNCONFIRMED_AND_SUSPICIOUS"}
                or c.get("inferred")
            )
            geocode_obj = result.get("geocode") or {}
            location = geocode_obj.get("location") or {}
            new_lat = location.get("latitude")
            new_lng = location.get("longitude")
            if new_lat is not None and new_lng is not None:
                out["new_lat"] = new_lat
                out["new_lng"] = new_lng
                if original_lat is not None and original_lng is not None:
                    out["distance_old_new_m"] = round(_haversine_m(original_lat, original_lng, new_lat, new_lng), 2)
                    out["geocode_changed"] = out["distance_old_new_m"] > 5.0  # 5m threshold
        elif resp.status_code == 403:
            out["error"] = f"403 Forbidden — Address Validation API likely not enabled. {resp.text[:200]}"
        else:
            out["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        out["error"] = f"request failed: {e}"

    if cache_path is not None:
        cache_path.write_text(json.dumps({
            "_schema_version": 1,
            "_created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": out,
        }, indent=2))

    return out
