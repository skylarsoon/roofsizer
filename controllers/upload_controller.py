import base64
import io

import numpy as np
from PIL import Image
from fastapi import UploadFile, HTTPException

from core.sam_predictor import get_predictor, get_inference_lock
from models.upload_models import UploadResponse
from services.geometry import extract_geometry


def _decode_image(contents: bytes) -> tuple[np.ndarray, int, int, int]:
    """Decode raw bytes into an RGB numpy array and return (array, H, W, C)."""
    try:
        image = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=422, detail="Could not decode image.")

    image_array = np.array(image)  # HxWx3, dtype uint8
    h, w, c = image_array.shape
    return image_array, h, w, c


def _mask_to_b64_png(mask: np.ndarray) -> str:
    """Convert a boolean HxW mask to a base64-encoded binary (0/255) PNG."""
    mask_img = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
    buf = io.BytesIO()
    mask_img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


async def handle_upload(file: UploadFile) -> UploadResponse:
    contents = await file.read()
    image_array, h, w, c = _decode_image(contents)

    # Center of the image as the foreground prompt point.
    # SAM2 expects (X, Y) == (col, row).
    cx, cy = w // 2, h // 2
    point_coords = np.array([[cx, cy]], dtype=np.float32)
    point_labels = np.array([1], dtype=np.int32)  # 1 = foreground

    predictor = get_predictor()
    lock = get_inference_lock()

    # set_image() + predict() must run atomically — predictor state is not
    # safe to share across concurrent calls.
    async with lock:
        predictor.set_image(image_array)
        masks, iou_scores, _ = predictor.predict(
            point_coords=point_coords,
            point_labels=point_labels,
            multimask_output=True,  # returns 3 candidates; pick best by IoU
        )

    # masks: (3, H, W) bool; iou_scores: (3,) float
    best_idx = int(np.argmax(iou_scores))
    best_mask: np.ndarray = masks[best_idx]        # (H, W) bool
    best_iou: float = float(iou_scores[best_idx])

    geometry = extract_geometry(best_mask)

    return UploadResponse(
        status="ok",
        filename=file.filename or "unknown",
        image_shape=[h, w, c],
        mask_b64=_mask_to_b64_png(best_mask),
        iou_score=best_iou,
        geometry=geometry,
    )
