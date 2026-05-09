"""Microsoft Building Footprints data source — wraps existing footprints.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import geopandas as gpd

from ..cache import Cache
from ..footprints import FootprintError, get_building_footprints_near_point


def fetch_footprints(
    address: str,
    lat: float,
    lng: float,
    buffer_meters: int,
    cache: Optional[Cache] = None,
) -> dict:
    """Fetch building footprints around a point.

    Returns a normalized envelope:
      {"source": "microsoft_footprints", "polygons_geojson_path": Path | None,
       "polygons_count": int, "metadata": {...}}
    """
    if cache is not None:
        cached_path = cache.get_footprints_path(address, buffer_meters)
        if cached_path is not None:
            gdf = gpd.read_file(cached_path)
            return {
                "source": "microsoft_footprints",
                "polygons_geojson_path": cached_path,
                "polygons_count": len(gdf),
                "metadata": {"buffer_m": buffer_meters, "cache": "hit"},
            }

    try:
        gdf = get_building_footprints_near_point(lat, lng, buffer_meters=buffer_meters)
    except FootprintError as e:
        return {
            "source": "microsoft_footprints",
            "polygons_geojson_path": None,
            "polygons_count": 0,
            "metadata": {"buffer_m": buffer_meters, "error": str(e)},
        }
    except Exception as e:
        # Catch transient PC / Azure Front Door errors so the whole run
        # doesn't crash on a 502 from Microsoft's side. Treat as no-data.
        msg = str(e)[:300]
        return {
            "source": "microsoft_footprints",
            "polygons_geojson_path": None,
            "polygons_count": 0,
            "metadata": {"buffer_m": buffer_meters, "error": f"transient PC error: {msg}"},
        }

    out_path: Optional[Path] = None
    if cache is not None:
        out_path = cache.footprints_path(address, buffer_meters)
        if gdf.empty:
            # write an empty FeatureCollection so the cache hit path still works
            out_path.write_text(json.dumps(
                {"type": "FeatureCollection", "features": []}
            ))
        else:
            gdf.to_file(out_path, driver="GeoJSON")
        cache.put_footprints_meta(address, buffer_meters)

    return {
        "source": "microsoft_footprints",
        "polygons_geojson_path": out_path,
        "polygons_count": len(gdf),
        "metadata": {"buffer_m": buffer_meters, "cache": "miss"},
    }
