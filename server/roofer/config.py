"""Environment loader and config validation."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

REQUIRED_VARS = ["GOOGLE_MAPS_API_KEY", "OPENAI_API_KEY"]
OPTIONAL_VARS = ["SAM2_CHECKPOINT", "SAM2_MODEL_CONFIG"]


@dataclass
class Config:
    google_maps_api_key: str
    openai_api_key: str
    openai_api_keys: list[str]  # all keys (primary + numbered extras), in order
    gemini_api_key: Optional[str]
    gemini_vision_model: str
    sam2_checkpoint: Optional[str]
    sam2_model_config: Optional[str]
    default_zoom: int
    default_scale: int
    default_image_size: str
    default_buffer_meters: int
    project_root: Path

    @property
    def outputs_dir(self) -> Path:
        return self.project_root / "outputs"

    @property
    def test_calls_dir(self) -> Path:
        return self.outputs_dir / "test_calls"

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"


class ConfigError(Exception):
    pass


def load_config(strict: bool = True) -> Config:
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    else:
        load_dotenv()

    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing and strict:
        raise ConfigError(
            f"Missing required env vars: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill them in."
        )

    # Collect all OPENAI_API_KEY* (primary + OPENAI_API_KEY2, OPENAI_API_KEY_2, etc.)
    primary = os.getenv("OPENAI_API_KEY", "")
    extras: list[str] = []
    import re as _re
    pat = _re.compile(r"^OPENAI_API_KEY(?:_?\d+)$")
    for k, v in sorted(os.environ.items()):
        if pat.match(k) and v and v.startswith("sk-"):
            extras.append(v)
    all_keys: list[str] = []
    if primary:
        all_keys.append(primary)
    for v in extras:
        if v not in all_keys:
            all_keys.append(v)

    cfg = Config(
        google_maps_api_key=os.getenv("GOOGLE_MAPS_API_KEY", ""),
        openai_api_key=primary,
        openai_api_keys=all_keys,
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_vision_model=os.getenv("GEMINI_VISION_MODEL", "gemini-3.1-pro-preview"),
        sam2_checkpoint=os.getenv("SAM2_CHECKPOINT") or None,
        sam2_model_config=os.getenv("SAM2_MODEL_CONFIG") or None,
        default_zoom=int(os.getenv("DEFAULT_ZOOM", "20")),
        default_scale=int(os.getenv("DEFAULT_SCALE", "2")),
        default_image_size=os.getenv("DEFAULT_IMAGE_SIZE", "640x640"),
        default_buffer_meters=int(os.getenv("DEFAULT_BUFFER_METERS", "150")),
        project_root=PROJECT_ROOT,
    )

    cfg.test_calls_dir.mkdir(parents=True, exist_ok=True)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)

    return cfg


def status_summary(cfg: Config) -> dict:
    """Return a redacted summary safe to print/log."""
    def mask(v: Optional[str]) -> str:
        if not v:
            return "MISSING"
        return f"set (len={len(v)})"
    return {
        "GOOGLE_MAPS_API_KEY": mask(cfg.google_maps_api_key),
        "OPENAI_API_KEY": mask(cfg.openai_api_key),
        "OPENAI_API_KEYS_TOTAL": str(len(cfg.openai_api_keys)),
        "GEMINI_API_KEY": mask(cfg.gemini_api_key),
        "GEMINI_VISION_MODEL": cfg.gemini_vision_model,
        "SAM2_CHECKPOINT": cfg.sam2_checkpoint or "MISSING",
        "SAM2_MODEL_CONFIG": cfg.sam2_model_config or "MISSING",
    }


if __name__ == "__main__":
    try:
        cfg = load_config(strict=False)
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    for k, v in status_summary(cfg).items():
        print(f"{k}: {v}")
