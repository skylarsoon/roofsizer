"""Google Static Maps data source — wraps imagery.py with caching."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from ..cache import Cache
from ..config import Config
from ..imagery import download_satellite_image


def fetch_satellite_image(
    address: str,
    lat: float,
    lng: float,
    cfg: Config,
    zoom: int,
    scale: int,
    size: str,
    cache: Optional[Cache] = None,
) -> dict:
    if cache is not None:
        cached = cache.get_imagery(address, zoom, scale, size)
        if cached is not None:
            return {
                "image_provider": "google_static_maps",
                "path": cached,
                "zoom": zoom,
                "scale": scale,
                "size": size,
                "cache": "hit",
            }

    if cache is not None:
        target_path = cache.put_imagery(address, zoom, scale, size)
    else:
        target_path = Path("outputs") / "tmp" / f"{abs(hash(address))}.png"
        target_path.parent.mkdir(parents=True, exist_ok=True)

    download_satellite_image(
        lat, lng, str(target_path), cfg,
        zoom=zoom, scale=scale, size=size,
    )

    return {
        "image_provider": "google_static_maps",
        "path": target_path,
        "zoom": zoom,
        "scale": scale,
        "size": size,
        "cache": "miss",
    }


def copy_to(out_path: Path, src: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, out_path)
    return out_path


def fetch_satellite_image_multi(
    address: str,
    lat: float,
    lng: float,
    cfg: Config,
    zooms: tuple[int, ...] = (19, 20, 21),
    scale: int = 2,
    size: str = "640x640",
    cache: Optional[Cache] = None,
) -> list[dict]:
    """Fetch the same property at multiple zoom levels (each cached separately).
    Returns a list of dicts in the same order as `zooms`."""
    out = []
    for z in zooms:
        try:
            meta = fetch_satellite_image(
                address=address, lat=lat, lng=lng, cfg=cfg,
                zoom=z, scale=scale, size=size, cache=cache,
            )
            out.append(meta)
        except Exception as e:
            out.append({
                "image_provider": "google_static_maps",
                "path": None,
                "zoom": z, "scale": scale, "size": size,
                "cache": "error",
                "error": str(e),
            })
    return out
