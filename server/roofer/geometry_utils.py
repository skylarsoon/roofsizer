"""Geometry helpers: bbox creation, area, distance, projection."""

from __future__ import annotations

import math
from typing import Tuple

from pyproj import Geod, Transformer
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

SQM_TO_SQFT = 10.7639
WGS84 = "EPSG:4326"
WEB_MERCATOR = "EPSG:3857"

_GEOD = Geod(ellps="WGS84")
_TO_3857 = Transformer.from_crs(WGS84, WEB_MERCATOR, always_xy=True)
_FROM_3857 = Transformer.from_crs(WEB_MERCATOR, WGS84, always_xy=True)


def utm_epsg_for(lat: float, lng: float) -> str:
    """Return the EPSG code for the UTM zone containing the point."""
    zone = int((lng + 180) // 6) + 1
    if lat >= 0:
        return f"EPSG:{32600 + zone}"
    return f"EPSG:{32700 + zone}"


def create_buffer_bbox(lat: float, lng: float, buffer_meters: float = 150) -> Tuple[float, float, float, float]:
    """Return (min_lng, min_lat, max_lng, max_lat) bbox in WGS84 around the point."""
    # Move ±buffer_meters N/S and E/W using geodesic forward calculation.
    # azimuths: 0=N, 90=E, 180=S, 270=W
    east_lng, east_lat, _ = _GEOD.fwd(lng, lat, 90, buffer_meters)
    west_lng, west_lat, _ = _GEOD.fwd(lng, lat, 270, buffer_meters)
    north_lng, north_lat, _ = _GEOD.fwd(lng, lat, 0, buffer_meters)
    south_lng, south_lat, _ = _GEOD.fwd(lng, lat, 180, buffer_meters)
    return (
        min(west_lng, east_lng),
        min(south_lat, north_lat),
        max(west_lng, east_lng),
        max(south_lat, north_lat),
    )


def polygon_area_sqft(geometry: BaseGeometry, lat_hint: float | None = None, lng_hint: float | None = None) -> float:
    """Compute polygon area in square feet. Input geometry assumed in EPSG:4326.
    Uses local UTM if hints provided, otherwise EPSG:3857 (less accurate at high lat)."""
    if lat_hint is not None and lng_hint is not None:
        epsg = utm_epsg_for(lat_hint, lng_hint)
        transformer = Transformer.from_crs(WGS84, epsg, always_xy=True)
    else:
        transformer = _TO_3857
    projected = transform(transformer.transform, geometry)
    return projected.area * SQM_TO_SQFT


def distance_to_point(geometry: BaseGeometry, lat: float, lng: float) -> float:
    """Distance in meters from geometry (EPSG:4326) to a point. Uses local UTM."""
    epsg = utm_epsg_for(lat, lng)
    transformer = Transformer.from_crs(WGS84, epsg, always_xy=True)
    projected_geom = transform(transformer.transform, geometry)
    px, py = transformer.transform(lng, lat)
    return projected_geom.distance(Point(px, py))


def bbox_polygon(bbox: Tuple[float, float, float, float]) -> Polygon:
    min_lng, min_lat, max_lng, max_lat = bbox
    return Polygon(
        [
            (min_lng, min_lat),
            (max_lng, min_lat),
            (max_lng, max_lat),
            (min_lng, max_lat),
            (min_lng, min_lat),
        ]
    )
