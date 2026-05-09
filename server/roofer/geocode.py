"""Google Geocoding API wrapper."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import requests

from .config import Config

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


class GeocodeError(Exception):
    pass


def geocode_address(address: str, cfg: Config, save_to: Optional[Path] = None) -> dict:
    """Geocode a street address. Returns a dict with formatted address, lat, lng, place_id."""
    params = {"address": address, "key": cfg.google_maps_api_key}
    resp = requests.get(GEOCODE_URL, params=params, timeout=15)

    if resp.status_code != 200:
        raise GeocodeError(f"HTTP {resp.status_code} from Google Geocoding API")

    payload = resp.json()
    status = payload.get("status")
    if status != "OK":
        raise GeocodeError(
            f"Geocoding API returned status={status}: {payload.get('error_message', '')}"
        )

    results = payload.get("results", [])
    if not results:
        raise GeocodeError(f"No geocoding results for: {address}")

    top = results[0]
    location = top["geometry"]["location"]
    out = {
        "input_address": address,
        "formatted_address": top.get("formatted_address"),
        "latitude": location["lat"],
        "longitude": location["lng"],
        "place_id": top.get("place_id"),
    }

    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        # Save the full payload for debugging, but with our cleaned summary on top
        with open(save_to, "w") as f:
            json.dump({"summary": out, "raw": payload}, f, indent=2)

    return out
