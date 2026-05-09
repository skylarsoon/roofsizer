import asyncio
import torch
from sam2.sam2_image_predictor import SAM2ImagePredictor

# Default model — hiera-small balances speed and accuracy well.
# Swap for "facebook/sam2-hiera-large" for higher quality at the cost of speed.
DEFAULT_MODEL_ID = "facebook/sam2-hiera-small"

_predictor: SAM2ImagePredictor | None = None
# Serializes set_image + predict calls across concurrent requests,
# because SAM2ImagePredictor mutates internal state between those two calls.
_inference_lock = asyncio.Lock()


def load_predictor(model_id: str = DEFAULT_MODEL_ID) -> None:
    global _predictor
    device = "cuda" if torch.cuda.is_available() else "cpu"
    _predictor = SAM2ImagePredictor.from_pretrained(model_id, device=device)
    _predictor.model.eval()


def get_predictor() -> SAM2ImagePredictor:
    if _predictor is None:
        raise RuntimeError("SAM2 predictor not initialized. Call load_predictor() at startup.")
    return _predictor


def get_inference_lock() -> asyncio.Lock:
    return _inference_lock
