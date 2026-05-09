from pydantic import BaseModel
from typing import List


class EdgeClassifications(BaseModel):
    eaves_px: float
    rakes_px: float
    ridge_px: float
    other_px: float


class RoofGeometry(BaseModel):
    pixel_area: float
    perimeter_px: float
    edge_classifications: EdgeClassifications
    contour: List[List[int]]   # [[x, y], ...]


class UploadResponse(BaseModel):
    status: str
    filename: str
    image_shape: List[int]    # [H, W, C]
    mask_b64: str             # base64-encoded binary PNG mask, same H×W as input
    iou_score: float          # SAM2's predicted mask quality (0–1)
    geometry: RoofGeometry
