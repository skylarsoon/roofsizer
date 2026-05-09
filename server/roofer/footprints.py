"""Microsoft Building Footprints access via Planetary Computer STAC.

Strategy (small-bbox only — never download the entire US):
- Query `ms-buildings` STAC for country-level items.
- The country partition is hive-partitioned by Bing zoom-9 quadkey.
- Compute the quadkey(s) covering our small bbox and read ONLY those
  partitions. Each z=9 partition is roughly 78 km wide at mid-latitudes.
- Clip results to the exact bbox before returning.

If Planetary Computer fails, raise FootprintError with a clear message.
The caller can then fall back to a manual Colorado-only download.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable, Optional

import geopandas as gpd
import pandas as pd
from shapely import wkb as shapely_wkb
from shapely.geometry import box

from .geometry_utils import (
    create_buffer_bbox,
    distance_to_point,
    polygon_area_sqft,
)

MS_BUILDINGS_COLLECTION = "ms-buildings"
QUADKEY_ZOOM = 9


class FootprintError(Exception):
    pass


def _lat_lng_to_quadkey(lat: float, lng: float, z: int = QUADKEY_ZOOM) -> str:
    sin_lat = math.sin(math.radians(lat))
    x = int(math.floor((lng + 180.0) / 360.0 * (1 << z)))
    y = int(
        math.floor(
            (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * (1 << z)
        )
    )
    digits: list[str] = []
    for i in range(z, 0, -1):
        digit = 0
        mask = 1 << (i - 1)
        if x & mask:
            digit += 1
        if y & mask:
            digit += 2
        digits.append(str(digit))
    return "".join(digits)


def _bbox_quadkeys(
    bbox: tuple[float, float, float, float], z: int = QUADKEY_ZOOM
) -> list[str]:
    min_lng, min_lat, max_lng, max_lat = bbox
    corners = [
        (min_lat, min_lng),
        (min_lat, max_lng),
        (max_lat, min_lng),
        (max_lat, max_lng),
    ]
    return sorted({_lat_lng_to_quadkey(la, lo, z) for la, lo in corners})


def _query_planetary_computer(bbox: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    try:
        import fsspec
        import planetary_computer as pc
        import pyarrow.parquet as pq
        from pystac_client import Client
    except ImportError as e:
        raise FootprintError(
            f"missing dependency for Planetary Computer access: {e}. "
            f"Run: pip install pystac-client planetary-computer pyarrow fsspec adlfs"
        )

    catalog = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=pc.sign_inplace,
    )
    items = list(
        catalog.search(collections=[MS_BUILDINGS_COLLECTION], bbox=bbox).items()
    )
    if not items:
        raise FootprintError(
            f"No ms-buildings STAC items found for bbox {bbox}. "
            f"This area may not be covered."
        )

    quadkeys = _bbox_quadkeys(bbox)
    bbox_geom = box(*bbox)
    frames: list[gpd.GeoDataFrame] = []

    # The collection has multiple snapshots over time; use the first item only.
    item = items[0]
    asset = pc.sign(item.assets["data"])
    storage_options = asset.extra_fields.get("table:storage_options", {})
    base_path = asset.href.replace("abfs://", "")
    fs = fsspec.filesystem("abfs", **storage_options)

    for qk in quadkeys:
        partition_path = f"{base_path}/quadkey={qk}"
        try:
            files = fs.ls(partition_path)
        except FileNotFoundError:
            continue
        parquet_files = [f for f in files if f.endswith(".parquet")]
        for pf_path in parquet_files:
            with fs.open(pf_path, "rb") as f:
                table = pq.read_table(f)
            # MS Buildings stores geometry as raw WKB in a single 'geometry'
            # column; decode it ourselves rather than relying on GeoArrow autodiscovery.
            wkb_blobs = table["geometry"].to_pylist()
            geometries = [shapely_wkb.loads(b) for b in wkb_blobs]
            gdf = gpd.GeoDataFrame({"geometry": geometries}, crs="EPSG:4326")
            gdf = gdf[gdf.intersects(bbox_geom)].copy()
            if not gdf.empty:
                frames.append(gdf)

    if not frames:
        # No buildings in any of the matching quadkeys — return an empty GeoDataFrame
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    combined = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True), crs="EPSG:4326"
    )
    return combined


def get_building_footprints_near_point(
    lat: float,
    lng: float,
    buffer_meters: int = 150,
) -> gpd.GeoDataFrame:
    """Return building footprints near a point as GeoDataFrame (EPSG:4326)."""
    bbox = create_buffer_bbox(lat, lng, buffer_meters)
    return _query_planetary_computer(bbox)


def summarize_footprints(
    gdf: gpd.GeoDataFrame,
    lat: float,
    lng: float,
    save_to: Optional[Path] = None,
) -> dict:
    """Compute area + distance for each polygon, identify the closest.
    Optionally save a GeoJSON to disk."""
    if gdf.empty:
        return {"count": 0, "polygons": [], "closest_index": None}

    rows = []
    for idx, geom in enumerate(gdf.geometry):
        area_sqft = polygon_area_sqft(geom, lat_hint=lat, lng_hint=lng)
        dist_m = distance_to_point(geom, lat, lng)
        rows.append(
            {
                "index": idx,
                "area_sqft": round(area_sqft, 1),
                "distance_m": round(dist_m, 2),
            }
        )

    rows.sort(key=lambda r: r["distance_m"])
    closest = rows[0]

    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        out = gdf.copy()
        out["area_sqft"] = [r["area_sqft"] for r in sorted(rows, key=lambda r: r["index"])]
        out["distance_m"] = [r["distance_m"] for r in sorted(rows, key=lambda r: r["index"])]
        out.to_file(save_to, driver="GeoJSON")

    return {
        "count": len(rows),
        "polygons": rows,
        "closest_index": closest["index"],
        "closest_area_sqft": closest["area_sqft"],
        "closest_distance_m": closest["distance_m"],
    }
