from pydantic import BaseModel
from typing import List


class UploadResponse(BaseModel):
    status: str
    filename: str
    image_shape: List[int]    # [H, W, C]
    mask_b64: str             # base64-encoded binary PNG mask, same H×W as input
    iou_score: float          # SAM2's predicted mask quality (0–1)
