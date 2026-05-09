"""SAM 2 single-building mask data source.

Takes a satellite image (cached) + lat/lng + optional seed polygon, returns
a building mask polygon in WGS84 plus a saved sam_mask.png artifact.

Caches binary masks at outputs/cache/sam/.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from ..cache import Cache, _addr_hash


class SamUnavailable(Exception):
    pass


_predictor_singleton = None


def _get_predictor(cfg):
    global _predictor_singleton
    if _predictor_singleton is not None:
        return _predictor_singleton
    if not cfg.sam2_checkpoint or not cfg.sam2_model_config:
        raise SamUnavailable("SAM2_CHECKPOINT / SAM2_MODEL_CONFIG not set")
    try:
        import torch
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
    except ImportError as e:
        raise SamUnavailable(f"sam2 / torch not importable: {e}")
    device = "cpu"
    try:
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
    except Exception:
        pass
    sam = build_sam2(cfg.sam2_model_config, cfg.sam2_checkpoint, device=device)
    _predictor_singleton = SAM2ImagePredictor(sam)
    _predictor_singleton._device_used = device  # type: ignore
    return _predictor_singleton


def _mercator_resolution(lat: float, zoom: int, scale: int) -> float:
    """Meters per pixel at the given lat/zoom/scale (Web Mercator)."""
    return 156543.03392 * math.cos(math.radians(lat)) / (2 ** zoom * scale)


def _pixel_to_lat_lng(px: float, py: float, *, center_lat: float, center_lng: float,
                      width: int, height: int, zoom: int, scale: int) -> tuple[float, float]:
    """Pixel offset → lat/lng using local mercator approximation around center."""
    mpp = _mercator_resolution(center_lat, zoom, scale)
    dx_m = (px - width / 2.0) * mpp
    dy_m = (py - height / 2.0) * mpp
    # Translate meters → lat/lng. Δlat ≈ dy / 111320; Δlng ≈ dx / (111320 * cos(lat))
    dlat = -dy_m / 111320.0  # image y increases downward = south
    dlng = dx_m / (111320.0 * max(0.01, math.cos(math.radians(center_lat))))
    return center_lat + dlat, center_lng + dlng


def _seed_hash(lat: float, lng: float, seed_polygon) -> str:
    if seed_polygon is None:
        s = f"point_{lat:.6f}_{lng:.6f}"
    else:
        c = seed_polygon.centroid
        s = f"poly_{c.x:.6f}_{c.y:.6f}_a{seed_polygon.area:.8f}"
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def mask_building(
    address: str,
    lat: float,
    lng: float,
    image_path: Path,
    cfg,
    cache: Optional[Cache] = None,
    seed_polygon=None,
    zoom: int = 20,
    scale: int = 2,
) -> dict:
    """Returns a normalized envelope:
    {"source": "sam", "polygons_geojson_path": Path | None,
     "polygons_count": int, "metadata": {...},
     "mask_png_path": Path | None}
    """
    if not image_path or not Path(image_path).exists():
        return {"source": "sam", "polygons_geojson_path": None, "polygons_count": 0,
                "mask_png_path": None,
                "metadata": {"error": f"image not found: {image_path}"}}

    image_path = Path(image_path)

    # Cache key
    cache_key = _seed_hash(lat, lng, seed_polygon)
    cache_dir = (cache.paths.root / "sam") if cache is not None else None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
    geojson_cache = cache_dir / f"{_addr_hash(address)}__z{zoom}_s{scale}_seed{cache_key}.geojson" if cache_dir else None
    mask_cache = cache_dir / f"{_addr_hash(address)}__z{zoom}_s{scale}_seed{cache_key}.npy" if cache_dir else None
    meta_cache = cache_dir / f"{_addr_hash(address)}__z{zoom}_s{scale}_seed{cache_key}.meta.json" if cache_dir else None

    if (cache is not None and not cache.refresh
            and geojson_cache and geojson_cache.exists()
            and mask_cache and mask_cache.exists()
            and meta_cache and meta_cache.exists()):
        try:
            meta = json.loads(meta_cache.read_text())
            if meta.get("_schema_version") == 1:
                return {
                    "source": "sam",
                    "polygons_geojson_path": geojson_cache,
                    "polygons_count": int(meta.get("polygons_count", 1)),
                    "mask_png_path": meta.get("mask_png_path"),
                    "metadata": {"cache": "hit", "device": meta.get("device")},
                }
        except Exception:
            pass

    # Load image as RGB
    img = Image.open(image_path).convert("RGB")
    img_np = np.array(img)
    H, W = img_np.shape[:2]

    # Build prompts
    point_coords = np.array([[W / 2.0, H / 2.0]], dtype=np.float32)
    point_labels = np.array([1], dtype=np.int32)

    mpp = _mercator_resolution(lat, zoom, scale)

    def latlng_to_px(la: float, lo: float) -> tuple[float, float]:
        dlat = la - lat
        dlng = lo - lng
        dy_m = -dlat * 111320.0
        dx_m = dlng * 111320.0 * max(0.01, math.cos(math.radians(lat)))
        return W / 2.0 + dx_m / mpp, H / 2.0 + dy_m / mpp

    box = None
    if seed_polygon is not None:
        try:
            min_lng, min_lat, max_lng, max_lat = seed_polygon.bounds
            x0, y0 = latlng_to_px(min_lat, min_lng)
            x1, y1 = latlng_to_px(max_lat, max_lng)
            xmin, xmax = sorted([x0, x1])
            ymin, ymax = sorted([y0, y1])
            # Pad the box a little so SAM has room to refine; clamp to image
            pad = 8.0
            xmin = max(0.0, xmin - pad); xmax = min(W - 1, xmax + pad)
            ymin = max(0.0, ymin - pad); ymax = min(H - 1, ymax + pad)
            box = np.array([xmin, ymin, xmax, ymax], dtype=np.float32)
        except Exception:
            box = None

    if box is None:
        # No seed polygon — default to a 35×35 m box around the image center.
        # At z=20 scale=2 lat=40°, mpp ≈ 0.057 m/px → 35m ≈ 614 px.
        half_m = 17.5
        half_px = half_m / mpp
        cx, cy = W / 2.0, H / 2.0
        xmin = max(0.0, cx - half_px); xmax = min(W - 1, cx + half_px)
        ymin = max(0.0, cy - half_px); ymax = min(H - 1, cy + half_px)
        box = np.array([xmin, ymin, xmax, ymax], dtype=np.float32)

    # Run SAM 2
    try:
        predictor = _get_predictor(cfg)
    except SamUnavailable as e:
        return {"source": "sam", "polygons_geojson_path": None, "polygons_count": 0,
                "mask_png_path": None,
                "metadata": {"error": str(e)}}

    try:
        predictor.set_image(img_np)
        masks, scores, _ = predictor.predict(
            point_coords=point_coords,
            point_labels=point_labels,
            box=box,
            multimask_output=True,
        )
    except Exception as e:
        return {"source": "sam", "polygons_geojson_path": None, "polygons_count": 0,
                "mask_png_path": None,
                "metadata": {"error": f"SAM inference failed: {e}"}}

    # Pick best mask, with sanity filter: reject masks that are obviously wrong.
    # A reasonable residential roof at z=20 scale=2 covers ~5%–25% of the image area.
    # Reject masks > 50% of image (whole-block segmentation) or < 1% (junk).
    if masks is None or len(masks) == 0:
        return {"source": "sam", "polygons_geojson_path": None, "polygons_count": 0,
                "mask_png_path": None,
                "metadata": {"error": "SAM returned 0 masks"}}
    img_area = float(H * W)
    ranked = sorted(range(len(masks)), key=lambda i: -float(scores[i]))
    chosen_idx = None
    rejection_log: list[str] = []
    for idx in ranked:
        m = masks[idx].astype(np.uint8)
        coverage = float(m.sum()) / img_area
        if coverage < 0.01:
            rejection_log.append(f"idx={idx} coverage {coverage:.3%} too small")
            continue
        if coverage > 0.50:
            rejection_log.append(f"idx={idx} coverage {coverage:.3%} too large")
            continue
        chosen_idx = idx
        break
    if chosen_idx is None:
        return {"source": "sam", "polygons_geojson_path": None, "polygons_count": 0,
                "mask_png_path": None,
                "metadata": {"error": "all SAM masks rejected by coverage filter",
                             "rejections": rejection_log}}
    best_idx = chosen_idx
    mask = masks[best_idx].astype(np.uint8)  # H x W binary

    # Largest contour → polygon
    try:
        import cv2
    except ImportError as e:
        return {"source": "sam", "polygons_geojson_path": None, "polygons_count": 0,
                "mask_png_path": None,
                "metadata": {"error": f"cv2 missing: {e}"}}
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {"source": "sam", "polygons_geojson_path": None, "polygons_count": 0,
                "mask_png_path": None,
                "metadata": {"error": "no contours from mask"}}
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 50:  # too tiny
        return {"source": "sam", "polygons_geojson_path": None, "polygons_count": 0,
                "mask_png_path": None,
                "metadata": {"error": "largest contour < 50 px"}}
    epsilon = 2.0
    simplified = cv2.approxPolyDP(largest, epsilon, True)
    if len(simplified) < 4:
        simplified = largest
    pixel_pts = simplified.reshape(-1, 2)

    # Convert pixel → WGS84
    wgs_pts = [_pixel_to_lat_lng(px, py, center_lat=lat, center_lng=lng,
                                 width=W, height=H, zoom=zoom, scale=scale)
               for px, py in pixel_pts]
    # shapely Polygon expects (lng, lat)
    coords = [(p[1], p[0]) for p in wgs_pts]
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    from shapely.geometry import Polygon as ShPoly
    import geopandas as gpd
    poly = ShPoly(coords)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty:
        return {"source": "sam", "polygons_geojson_path": None, "polygons_count": 0,
                "mask_png_path": None,
                "metadata": {"error": "produced empty polygon after reprojection"}}

    # Unconditional residential-area gate. SAM has been observed to segment
    # entire blocks (50k+ sqft) or tiny noise (50 sqft). Reject either case
    # at the source so no downstream caller has to.
    from ..geometry_utils import polygon_area_sqft as _area_sqft
    sam_area_sqft = _area_sqft(poly, lat_hint=lat, lng_hint=lng)
    if sam_area_sqft < 600 or sam_area_sqft > 8000:
        return {"source": "sam", "polygons_geojson_path": None, "polygons_count": 0,
                "mask_png_path": None,
                "metadata": {
                    "error": f"SAM area {sam_area_sqft:.0f} sqft outside residential range [600, 8000]",
                    "rejected_area_sqft": round(sam_area_sqft, 1),
                }}

    # Save artifacts
    geojson_path = geojson_cache
    mask_png_path = None
    if cache_dir is not None:
        gdf = gpd.GeoDataFrame({"source": ["sam"]}, geometry=[poly], crs="EPSG:4326")
        gdf.to_file(geojson_path, driver="GeoJSON")
        np.save(mask_cache, mask)
        # Save the mask as PNG for visualization
        mask_png_path = geojson_path.with_suffix(".png")
        Image.fromarray((mask * 255).astype(np.uint8)).save(mask_png_path)
        meta_cache.write_text(json.dumps({
            "_schema_version": 1,
            "_created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "address": address, "zoom": zoom, "scale": scale,
            "device": getattr(predictor, "_device_used", "?"),
            "polygons_count": 1,
            "mask_png_path": str(mask_png_path),
        }, indent=2))

    return {
        "source": "sam",
        "polygons_geojson_path": geojson_path,
        "polygons_count": 1,
        "mask_png_path": mask_png_path,
        "metadata": {
            "cache": "miss",
            "device": getattr(predictor, "_device_used", "?"),
            "score": float(scores[best_idx]),
        },
    }
