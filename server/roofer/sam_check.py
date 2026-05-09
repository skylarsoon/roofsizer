"""SAM 2 availability check — does NOT run segmentation."""

from __future__ import annotations

from pathlib import Path

from .config import Config


def check_sam2(cfg: Config) -> dict:
    out = {
        "import_ok": False,
        "checkpoint_set": bool(cfg.sam2_checkpoint),
        "checkpoint_exists": False,
        "config_set": bool(cfg.sam2_model_config),
        "config_exists": False,
        "messages": [],
    }

    try:
        import sam2  # noqa: F401
        out["import_ok"] = True
    except ImportError as e:
        out["messages"].append(
            f"sam2 not importable ({e}). Install with:\n"
            f"  pip install git+https://github.com/facebookresearch/sam2.git"
        )

    if cfg.sam2_checkpoint:
        path = Path(cfg.sam2_checkpoint).expanduser()
        out["checkpoint_path"] = str(path)
        out["checkpoint_exists"] = path.exists() and path.is_file()
        if not out["checkpoint_exists"]:
            out["messages"].append(f"SAM2_CHECKPOINT does not exist: {path}")
    else:
        out["messages"].append("SAM2_CHECKPOINT not set in .env")

    if cfg.sam2_model_config:
        cfg_path = Path(cfg.sam2_model_config).expanduser()
        out["config_path"] = str(cfg_path)
        # Config can be a file path or a hydra config name; only flag missing if it
        # looks like a filesystem path.
        if "/" in cfg.sam2_model_config or "\\" in cfg.sam2_model_config:
            out["config_exists"] = cfg_path.exists()
            if not out["config_exists"]:
                out["messages"].append(f"SAM2_MODEL_CONFIG path does not exist: {cfg_path}")
        else:
            out["config_exists"] = True  # assume it's a hydra config name
            out["messages"].append(
                f"SAM2_MODEL_CONFIG looks like a config name, not a path: {cfg.sam2_model_config}"
            )
    else:
        out["messages"].append("SAM2_MODEL_CONFIG not set in .env")

    out["ready"] = (
        out["import_ok"] and out["checkpoint_exists"] and out["config_exists"]
    )
    return out
