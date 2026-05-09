"""Disk cache for geocode / imagery / footprints.

All cache files are scenario-independent and keyed on the normalized address
(plus relevant query params for imagery/footprints). Each cache entry includes
`_schema_version` and `_created_at` so we can invalidate safely.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_address(address: str) -> str:
    return re.sub(r"\s+", " ", address.strip()).lower()


def _addr_hash(address: str) -> str:
    return hashlib.sha1(normalize_address(address).encode("utf-8")).hexdigest()[:16]


@dataclass
class CachePaths:
    root: Path

    @property
    def geocode_dir(self) -> Path:
        return self.root / "geocode"

    @property
    def imagery_dir(self) -> Path:
        return self.root / "imagery"

    @property
    def footprints_dir(self) -> Path:
        return self.root / "footprints"

    def ensure(self) -> None:
        for d in (self.geocode_dir, self.imagery_dir, self.footprints_dir):
            d.mkdir(parents=True, exist_ok=True)


class Cache:
    def __init__(self, root: Path, refresh: bool = False):
        self.paths = CachePaths(root=root)
        self.paths.ensure()
        self.refresh = refresh

    # ---- geocode ----
    def geocode_path(self, address: str) -> Path:
        return self.paths.geocode_dir / f"{_addr_hash(address)}.json"

    def get_geocode(self, address: str) -> Optional[dict]:
        if self.refresh:
            return None
        p = self.geocode_path(address)
        if not p.exists():
            return None
        try:
            payload = json.loads(p.read_text())
            if payload.get("_schema_version") != SCHEMA_VERSION:
                return None
            return payload["data"]
        except Exception:
            return None

    def put_geocode(self, address: str, data: dict) -> None:
        p = self.geocode_path(address)
        p.write_text(json.dumps(
            {"_schema_version": SCHEMA_VERSION, "_created_at": _now_iso(), "data": data},
            indent=2,
        ))

    # ---- imagery ----
    def imagery_path(self, address: str, zoom: int, scale: int, size: str) -> Path:
        return self.paths.imagery_dir / f"{_addr_hash(address)}__z{zoom}_s{scale}_{size}.png"

    def imagery_meta_path(self, address: str, zoom: int, scale: int, size: str) -> Path:
        p = self.imagery_path(address, zoom, scale, size)
        return p.with_suffix(".meta.json")

    def get_imagery(self, address: str, zoom: int, scale: int, size: str) -> Optional[Path]:
        if self.refresh:
            return None
        p = self.imagery_path(address, zoom, scale, size)
        meta = self.imagery_meta_path(address, zoom, scale, size)
        if not (p.exists() and meta.exists()):
            return None
        try:
            payload = json.loads(meta.read_text())
            if payload.get("_schema_version") != SCHEMA_VERSION:
                return None
            return p
        except Exception:
            return None

    def put_imagery(self, address: str, zoom: int, scale: int, size: str) -> Path:
        # Returns the path the caller should write the image bytes to; meta is
        # written here so we know the file is complete.
        p = self.imagery_path(address, zoom, scale, size)
        meta = self.imagery_meta_path(address, zoom, scale, size)
        meta.write_text(json.dumps(
            {"_schema_version": SCHEMA_VERSION, "_created_at": _now_iso(),
             "address": address, "zoom": zoom, "scale": scale, "size": size},
            indent=2,
        ))
        return p

    # ---- footprints ----
    def footprints_path(self, address: str, buffer_m: int) -> Path:
        return self.paths.footprints_dir / f"{_addr_hash(address)}__buf{buffer_m}.geojson"

    def footprints_meta_path(self, address: str, buffer_m: int) -> Path:
        p = self.footprints_path(address, buffer_m)
        return p.with_suffix(".meta.json")

    def get_footprints_path(self, address: str, buffer_m: int) -> Optional[Path]:
        if self.refresh:
            return None
        p = self.footprints_path(address, buffer_m)
        meta = self.footprints_meta_path(address, buffer_m)
        if not (p.exists() and meta.exists()):
            return None
        try:
            payload = json.loads(meta.read_text())
            if payload.get("_schema_version") != SCHEMA_VERSION:
                return None
            return p
        except Exception:
            return None

    def put_footprints_meta(self, address: str, buffer_m: int) -> None:
        meta = self.footprints_meta_path(address, buffer_m)
        meta.write_text(json.dumps(
            {"_schema_version": SCHEMA_VERSION, "_created_at": _now_iso(),
             "address": address, "buffer_m": buffer_m},
            indent=2,
        ))
