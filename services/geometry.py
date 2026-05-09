import math

import cv2
import numpy as np

# Angle thresholds (degrees from horizontal) for edge classification.
_HORIZONTAL_MAX = 20.0   # <= 20°  → horizontal (eave or ridge)
_RAKE_MAX = 70.0          # 20–70°  → sloped perimeter (rake)
                          # > 70°   → nearly vertical → other


def extract_geometry(mask: np.ndarray) -> dict:
    """
    Takes a boolean (H, W) SAM 2 mask and returns measurable roof geometry in pixels.

    Returns:
        {
            "pixel_area": float,
            "perimeter_px": float,
            "edge_classifications": {
                "eaves_px": float,   # horizontal edges on the lower half
                "rakes_px": float,   # sloped perimeter edges (20°–70°)
                "ridge_px": float,   # horizontal edges on the upper half
                "other_px": float,   # nearly vertical or unclassified
            },
            "contour": [[x, y], ...]  # largest contour as serializable points
        }
    """
    mask_u8 = (mask.astype(np.uint8)) * 255
    h, w = mask_u8.shape

    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return _empty_result()

    # The roof is the largest contour by enclosed area.
    largest = max(contours, key=cv2.contourArea)

    pixel_area = float(cv2.contourArea(largest))
    perimeter_px = float(cv2.arcLength(largest, closed=True))

    # largest has shape (N, 1, 2); squeeze to (N, 2) array of (x, y) pairs.
    pts = largest[:, 0, :]
    n = len(pts)

    eaves_px = 0.0
    rakes_px = 0.0
    ridge_px = 0.0
    other_px = 0.0

    for i in range(n):
        x1, y1 = float(pts[i][0]), float(pts[i][1])
        x2, y2 = float(pts[(i + 1) % n][0]), float(pts[(i + 1) % n][1])

        edge_len = math.hypot(x2 - x1, y2 - y1)
        if edge_len == 0:
            continue

        # Angle from horizontal: 0° = flat, 90° = vertical.
        angle = math.degrees(math.atan2(abs(y2 - y1), abs(x2 - x1)))

        mid_y = (y1 + y2) / 2.0

        if angle <= _HORIZONTAL_MAX:
            # Horizontal edge — distinguish eave (lower) from ridge (upper).
            if mid_y > h / 2:
                eaves_px += edge_len
            else:
                ridge_px += edge_len
        elif angle <= _RAKE_MAX:
            rakes_px += edge_len
        else:
            other_px += edge_len

    return {
        "pixel_area": round(pixel_area, 2),
        "perimeter_px": round(perimeter_px, 2),
        "edge_classifications": {
            "eaves_px": round(eaves_px, 2),
            "rakes_px": round(rakes_px, 2),
            "ridge_px": round(ridge_px, 2),
            "other_px": round(other_px, 2),
        },
        "contour": pts.tolist(),
    }


def _empty_result() -> dict:
    return {
        "pixel_area": 0.0,
        "perimeter_px": 0.0,
        "edge_classifications": {
            "eaves_px": 0.0,
            "rakes_px": 0.0,
            "ridge_px": 0.0,
            "other_px": 0.0,
        },
        "contour": [],
    }
