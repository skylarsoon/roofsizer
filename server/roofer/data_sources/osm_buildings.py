"""OSM Overpass building footprints — fallback for properties where MS PC has no polygons.

Free, no auth. Returns the same normalized envelope as `microsoft_footprints.fetch_footprints`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import geopandas as gpd
import requests
from shapely.geometry import MultiPolygon, Polygon, shape

from ..cache import Cache, _addr_hash
from ..geometry_utils import create_buffer_bbox

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_FALLBACKS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]


class OsmError(Exception):
    pass


def _build_query(bbox: tuple[float, float, float, float]) -> str:
    # bbox = (min_lng, min_lat, max_lng, max_lat) — Overpass wants (south, west, north, east)
    min_lng, min_lat, max_lng, max_lat = bbox
    return (
        f"[out:json][timeout:25];"
        f"("
        f'  way["building"]({min_lat},{min_lng},{max_lat},{max_lng});'
        f'  relation["building"]({min_lat},{min_lng},{max_lat},{max_lng});'
        f");"
        f"out geom;"
    )


def _ring_to_coords(geometry_nodes: list[dict]) -> list[tuple[float, float]]:
    return [(n["lon"], n["lat"]) for n in geometry_nodes]


def _way_to_polygon(elem: dict) -> Optional[Polygon]:
    geom = elem.get("geometry")
    if not geom:
        return None
    coords = _ring_to_coords(geom)
    if len(coords) < 4:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    try:
        poly = Polygon(coords)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area == 0:
            return None
        return poly
    except Exception:
        return None


def _relation_to_geom(elem: dict) -> Optional[Polygon | MultiPolygon]:
    members = elem.get("members") or []
    outers: list[Polygon] = []
    inners: list[Polygon] = []
    for m in members:
        role = m.get("role") or ""
        nodes = m.get("geometry")
        if not nodes:
            continue
        coords = _ring_to_coords(nodes)
        if len(coords) < 4:
            continue
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        try:
            poly = Polygon(coords)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue
            if role == "outer":
                outers.append(poly)
            elif role == "inner":
                inners.append(poly)
        except Exception:
            continue
    if not outers:
        return None
    # Subtract inners from outers
    pieces: list[Polygon] = []
    for o in outers:
        residual = o
        for i in inners:
            try:
                if residual.intersects(i):
                    residual = residual.difference(i)
            except Exception:
                pass
        if isinstance(residual, (Polygon, MultiPolygon)) and not residual.is_empty:
            pieces.append(residual)
    if not pieces:
        return None
    if len(pieces) == 1:
        return pieces[0]
    return MultiPolygon([p for p in pieces if isinstance(p, Polygon)])


def _query_overpass(bbox: tuple[float, float, float, float], timeout: int = 30) -> dict:
    query = _build_query(bbox)
    last_err: Optional[Exception] = None
    for url in [OVERPASS_URL] + OVERPASS_FALLBACKS:
        try:
            resp = requests.post(url, data={"data": query}, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            last_err = OsmError(f"HTTP {resp.status_code} from {url}: {resp.text[:200]}")
        except Exception as e:
            last_err = e
        time.sleep(0.5)
    raise OsmError(f"all Overpass endpoints failed: {last_err}")


def fetch_footprints(
    address: str,
    lat: float,
    lng: float,
    buffer_meters: int,
    cache: Optional[Cache] = None,
) -> dict:
    """Fetch OSM building footprints around a point. Same envelope as MS source."""
    cache_key_path: Optional[Path] = None
    cache_meta_path: Optional[Path] = None
    if cache is not None:
        osm_dir = cache.paths.root / "osm"
        osm_dir.mkdir(parents=True, exist_ok=True)
        cache_key_path = osm_dir / f"{_addr_hash(address)}__buf{buffer_meters}.geojson"
        cache_meta_path = cache_key_path.with_suffix(".meta.json")
        if not cache.refresh and cache_key_path.exists() and cache_meta_path.exists():
            try:
                meta = json.loads(cache_meta_path.read_text())
                if meta.get("_schema_version") == 1:
                    gdf = gpd.read_file(cache_key_path)
                    return {
                        "source": "osm",
                        "polygons_geojson_path": cache_key_path,
                        "polygons_count": len(gdf),
                        "metadata": {"buffer_m": buffer_meters, "cache": "hit"},
                    }
            except Exception:
                pass

    bbox = create_buffer_bbox(lat, lng, buffer_meters)
    try:
        payload = _query_overpass(bbox)
    except Exception as e:
        return {
            "source": "osm",
            "polygons_geojson_path": None,
            "polygons_count": 0,
            "metadata": {"buffer_m": buffer_meters, "error": str(e)},
        }

    geometries: list = []
    for elem in payload.get("elements", []):
        etype = elem.get("type")
        if etype == "way":
            geom = _way_to_polygon(elem)
        elif etype == "relation":
            geom = _relation_to_geom(elem)
        else:
            geom = None
        if geom is not None:
            geometries.append(geom)

    if not geometries:
        gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    else:
        gdf = gpd.GeoDataFrame(geometry=geometries, crs="EPSG:4326")

    if cache_key_path is not None:
        if gdf.empty:
            cache_key_path.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
        else:
            gdf.to_file(cache_key_path, driver="GeoJSON")
        from datetime import datetime, timezone
        cache_meta_path.write_text(json.dumps({
            "_schema_version": 1,
            "_created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "address": address, "buffer_m": buffer_meters, "source": "osm",
        }, indent=2))

    return {
        "source": "osm",
        "polygons_geojson_path": cache_key_path,
        "polygons_count": len(gdf),
        "metadata": {"buffer_m": buffer_meters, "cache": "miss"},
    }
