"""Google Street View Static API — thin coverage probe (Phase 4 Tier A).

Calls the metadata endpoint (free, no quota cost) to record whether Street View
imagery exists for a location. Actual image downloads + LLM pitch extraction
happen later in Phase 4 Tier C.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from ..cache import Cache, _addr_hash

METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
IMAGE_URL = "https://maps.googleapis.com/maps/api/streetview"


def fetch_streetview_image(
    address: str,
    lat: float,
    lng: float,
    api_key: str,
    cache: Optional[Cache] = None,
    refresh: bool = False,
    heading: Optional[int] = None,  # 0-359; if None, Street View picks best
    fov: int = 90,
    size: str = "640x640",
) -> dict:
    """Fetch the actual Street View image. Cached.

    Returns: {available, path: Path | None, error, metadata}
    """
    cache_dir: Optional[Path] = None
    cache_key_path: Optional[Path] = None
    cache_meta_path: Optional[Path] = None
    if cache is not None:
        cache_dir = cache.paths.root / "streetview_images"
        cache_dir.mkdir(parents=True, exist_ok=True)
        h_str = "auto" if heading is None else str(heading)
        cache_key_path = cache_dir / f"{_addr_hash(address)}__h{h_str}_fov{fov}_{size}.jpg"
        cache_meta_path = cache_key_path.with_suffix(".meta.json")
        if not refresh and cache_key_path.exists() and cache_meta_path.exists():
            try:
                meta = json.loads(cache_meta_path.read_text())
                if meta.get("_schema_version") == 1:
                    return {
                        "available": True,
                        "path": cache_key_path,
                        "error": None,
                        "metadata": meta,
                    }
            except Exception:
                pass

    import requests
    params = {
        "location": f"{lat},{lng}",
        "size": size,
        "fov": str(fov),
        "source": "default",
        "key": api_key,
    }
    if heading is not None:
        params["heading"] = str(heading)
    try:
        resp = requests.get(IMAGE_URL, params=params, timeout=15)
        if resp.status_code != 200:
            return {"available": False, "path": None,
                    "error": f"HTTP {resp.status_code}: {resp.text[:200]}", "metadata": {}}
        ctype = resp.headers.get("content-type", "")
        if not ctype.startswith("image/"):
            return {"available": False, "path": None,
                    "error": f"non-image response: {ctype}, {resp.text[:200]}", "metadata": {}}
        data = resp.content
    except Exception as e:
        return {"available": False, "path": None, "error": f"request failed: {e}", "metadata": {}}

    if cache_key_path is not None:
        cache_key_path.write_bytes(data)
        from datetime import datetime, timezone
        cache_meta_path.write_text(json.dumps({
            "_schema_version": 1,
            "_created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "address": address, "heading": heading, "fov": fov, "size": size,
        }, indent=2))

    return {
        "available": True,
        "path": cache_key_path,
        "error": None,
        "metadata": {"heading": heading, "fov": fov, "size": size},
    }


def fetch_streetview_coverage(
    address: str,
    lat: float,
    lng: float,
    api_key: str,
    cache: Optional[Cache] = None,
    refresh: bool = False,
) -> dict:
    """Probe Street View metadata. Never raises.

    Returns: {
      address, lat, lng,
      streetview_available: bool,
      pano_id: str | None,
      pano_lat, pano_lng,
      distance_to_pano_m: float | None,
      pano_date: str | None,
      copyright: str | None,
      status: str,
      error: str | None,
    }
    """
    cache_dir: Optional[Path] = None
    cache_path: Optional[Path] = None
    if cache is not None:
        cache_dir = cache.paths.root / "streetview"
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
        "address": address, "lat": lat, "lng": lng,
        "streetview_available": False,
        "pano_id": None,
        "pano_lat": None, "pano_lng": None,
        "distance_to_pano_m": None,
        "pano_date": None,
        "copyright": None,
        "status": None,
        "error": None,
    }

    try:
        resp = requests.get(
            METADATA_URL,
            params={
                "location": f"{lat},{lng}",
                "radius": 50,
                "source": "default",
                "key": api_key,
            },
            timeout=10,
        )
        out["status"] = str(resp.status_code)
        if resp.status_code == 200:
            j = resp.json()
            status = j.get("status")
            out["status"] = status
            if status == "OK":
                out["streetview_available"] = True
                out["pano_id"] = j.get("pano_id")
                loc = j.get("location") or {}
                out["pano_lat"] = loc.get("lat")
                out["pano_lng"] = loc.get("lng")
                if out["pano_lat"] is not None and out["pano_lng"] is not None:
                    # Compute Haversine-lite distance in meters.
                    import math
                    dlat = (out["pano_lat"] - lat) * 111320.0
                    dlng = (out["pano_lng"] - lng) * 111320.0 * max(0.01, math.cos(math.radians(lat)))
                    out["distance_to_pano_m"] = round(math.hypot(dlat, dlng), 2)
                out["pano_date"] = j.get("date")
                out["copyright"] = j.get("copyright")
            elif status in {"ZERO_RESULTS", "NOT_FOUND"}:
                out["error"] = "no_streetview_coverage"
            elif status == "REQUEST_DENIED":
                out["error"] = f"403/REQUEST_DENIED — Street View Static likely not enabled. {j.get('error_message', '')}"
            else:
                out["error"] = f"status={status} — {j.get('error_message', '')}"
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
