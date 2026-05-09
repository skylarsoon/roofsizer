"""Pick the polygon(s) that represent the target residential building."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .geometry_utils import distance_to_point, polygon_area_sqft


@dataclass
class Selection:
    geometry: BaseGeometry  # WGS84
    area_sqft: float
    distance_m: float
    selection_reason: str
    candidates: list[dict]  # top-N candidates as {index, area_sqft, distance_m}


def _candidates(gdf: gpd.GeoDataFrame, lat: float, lng: float) -> list[dict]:
    rows: list[dict] = []
    for idx, geom in enumerate(gdf.geometry):
        if geom is None or geom.is_empty:
            continue
        area = polygon_area_sqft(geom, lat_hint=lat, lng_hint=lng)
        dist = distance_to_point(geom, lat, lng)
        rows.append({"index": int(idx), "area_sqft": round(area, 1), "distance_m": round(dist, 2)})
    rows.sort(key=lambda r: r["distance_m"])
    return rows


def pick_closest(gdf: gpd.GeoDataFrame, lat: float, lng: float) -> Optional[Selection]:
    if gdf.empty:
        return None
    cands = _candidates(gdf, lat, lng)
    if not cands:
        return None
    top = cands[0]
    geom = gdf.geometry.iloc[top["index"]]
    return Selection(
        geometry=geom,
        area_sqft=top["area_sqft"],
        distance_m=top["distance_m"],
        selection_reason="closest polygon to geocoded point",
        candidates=cands[:5],
    )


def pick_residential(
    gdf: gpd.GeoDataFrame,
    lat: float,
    lng: float,
    max_distance_m: float = 25.0,
    min_area_sqft: float = 800.0,
) -> Optional[Selection]:
    """Prefer a polygon ≤ 25m AND ≥ 800 sqft. Fall back to closest if no candidate qualifies."""
    if gdf.empty:
        return None
    cands = _candidates(gdf, lat, lng)
    if not cands:
        return None

    qualifying = [c for c in cands if c["distance_m"] <= max_distance_m and c["area_sqft"] >= min_area_sqft]
    if qualifying:
        # closest among qualifying
        top = qualifying[0]
        geom = gdf.geometry.iloc[top["index"]]
        return Selection(
            geometry=geom,
            area_sqft=top["area_sqft"],
            distance_m=top["distance_m"],
            selection_reason=f"closest polygon within {max_distance_m:.0f}m AND area>={min_area_sqft:.0f} sqft",
            candidates=cands[:5],
        )

    # fall back to closest
    top = cands[0]
    geom = gdf.geometry.iloc[top["index"]]
    return Selection(
        geometry=geom,
        area_sqft=top["area_sqft"],
        distance_m=top["distance_m"],
        selection_reason=(
            f"no polygon met distance<={max_distance_m:.0f}m AND area>={min_area_sqft:.0f} sqft; "
            f"falling back to closest"
        ),
        candidates=cands[:5],
    )


def pick_residential_strict(
    gdf: gpd.GeoDataFrame,
    lat: float,
    lng: float,
    max_distance_m: float = 25.0,
    min_area_sqft: float = 600.0,
    max_area_sqft: float = 8000.0,
) -> Optional[Selection]:
    """Like pick_residential but rejects polygons larger than `max_area_sqft`
    (which usually means commercial / multi-unit / merged building cluster)."""
    if gdf.empty:
        return None
    cands = _candidates(gdf, lat, lng)
    if not cands:
        return None

    qualifying = [c for c in cands
                  if c["distance_m"] <= max_distance_m
                  and min_area_sqft <= c["area_sqft"] <= max_area_sqft]
    if qualifying:
        top = qualifying[0]
        geom = gdf.geometry.iloc[top["index"]]
        return Selection(
            geometry=geom,
            area_sqft=top["area_sqft"],
            distance_m=top["distance_m"],
            selection_reason=(
                f"closest polygon within {max_distance_m:.0f}m AND area in "
                f"[{min_area_sqft:.0f}, {max_area_sqft:.0f}] sqft"
            ),
            candidates=cands[:5],
        )

    # Fallback: closest, but warn
    top = cands[0]
    geom = gdf.geometry.iloc[top["index"]]
    return Selection(
        geometry=geom,
        area_sqft=top["area_sqft"],
        distance_m=top["distance_m"],
        selection_reason=(
            f"no polygon met distance<={max_distance_m:.0f}m AND area in "
            f"[{min_area_sqft:.0f}, {max_area_sqft:.0f}] sqft; falling back to closest"
        ),
        candidates=cands[:5],
    )


def pick_all_within(
    gdf: gpd.GeoDataFrame,
    lat: float,
    lng: float,
    radius_m: float = 25.0,
    min_area_sqft: float = 200.0,
) -> Optional[Selection]:
    """Union of polygons that anchor to the closest residential building.
    Adds neighbors only if they're directly attached to the main polygon
    (within `attach_buffer_m` of it), so we capture attached/detached garages
    without picking up the neighbor's house.
    """
    if gdf.empty:
        return None
    cands = _candidates(gdf, lat, lng)
    if not cands:
        return None

    # Anchor polygon: closest one within radius_m AND area > min_area_sqft.
    anchor = next((c for c in cands
                   if c["distance_m"] <= radius_m and c["area_sqft"] >= min_area_sqft),
                  None)
    if anchor is None:
        return None
    anchor_geom = gdf.geometry.iloc[anchor["index"]]

    # Project the anchor to a meter CRS so we can dilate by a small distance.
    from .geometry_utils import utm_epsg_for, WGS84
    from pyproj import Transformer
    from shapely.ops import transform
    epsg = utm_epsg_for(lat, lng)
    to_m = Transformer.from_crs(WGS84, epsg, always_xy=True)
    from_m = Transformer.from_crs(epsg, WGS84, always_xy=True)
    anchor_m = transform(to_m.transform, anchor_geom)

    # Attach radius: anything within ~3 m of the anchor in projected meters.
    attach_buffer_m = 3.0
    attach_zone = anchor_m.buffer(attach_buffer_m)

    # Collect anchor + every other polygon that intersects the attach zone
    # AND is itself within radius_m of the geocoded point AND area > 80 sqft.
    selected_idxs = [anchor["index"]]
    for c in cands:
        if c["index"] == anchor["index"]:
            continue
        if c["distance_m"] > radius_m:
            continue
        if c["area_sqft"] < 80:
            continue
        cand_m = transform(to_m.transform, gdf.geometry.iloc[c["index"]])
        if cand_m.intersects(attach_zone):
            selected_idxs.append(c["index"])

    geoms = [gdf.geometry.iloc[i] for i in selected_idxs]
    union = unary_union(geoms)
    area_total = polygon_area_sqft(union, lat_hint=lat, lng_hint=lng)
    return Selection(
        geometry=union,
        area_sqft=round(area_total, 1),
        distance_m=anchor["distance_m"],
        selection_reason=(
            f"union of anchor + {len(selected_idxs) - 1} attached polygon(s) "
            f"within {attach_buffer_m:.0f}m of anchor"
        ),
        candidates=cands[:5],
    )
