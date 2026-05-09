"""Google Static Maps API wrapper."""

from __future__ import annotations

from pathlib import Path

import requests

from .config import Config

STATIC_MAP_URL = "https://maps.googleapis.com/maps/api/staticmap"


class ImageryError(Exception):
    pass


def download_satellite_image(
    lat: float,
    lng: float,
    output_path: str | Path,
    cfg: Config,
    zoom: int = 20,
    scale: int = 2,
    size: str = "640x640",
) -> str:
    """Download a satellite image centered on lat/lng. Returns absolute file path."""
    params = {
        "center": f"{lat},{lng}",
        "zoom": str(zoom),
        "size": size,
        "scale": str(scale),
        "maptype": "satellite",
        "key": cfg.google_maps_api_key,
    }
    resp = requests.get(STATIC_MAP_URL, params=params, timeout=30)

    if resp.status_code != 200:
        raise ImageryError(
            f"HTTP {resp.status_code} from Static Maps API: {resp.text[:200]}"
        )

    if not resp.headers.get("content-type", "").startswith("image/"):
        raise ImageryError(
            f"Static Maps did not return an image. content-type={resp.headers.get('content-type')}, "
            f"body={resp.text[:200]}"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(resp.content)
    return str(output_path.resolve())
