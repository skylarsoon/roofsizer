"""Minimal OpenAI connection tests (text + optional image)."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Optional

from .config import Config

TEXT_MODEL = "gpt-4o-mini"
VISION_MODEL = "gpt-4o-mini"


class OpenAIError(Exception):
    pass


def _client(cfg: Config):
    try:
        from openai import OpenAI
    except ImportError as e:
        raise OpenAIError(f"openai package not installed: {e}. Run: pip install openai")
    return OpenAI(api_key=cfg.openai_api_key)


def test_text(cfg: Config, save_to: Optional[Path] = None) -> dict:
    client = _client(cfg)
    resp = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {
                "role": "user",
                "content": (
                    "Reply with EXACTLY this JSON and nothing else: "
                    '{"status":"ok"}'
                ),
            }
        ],
        max_tokens=20,
        temperature=0,
    )
    content = resp.choices[0].message.content or ""
    out = {
        "model": TEXT_MODEL,
        "raw_content": content,
        "tokens": {
            "prompt": resp.usage.prompt_tokens if resp.usage else None,
            "completion": resp.usage.completion_tokens if resp.usage else None,
        },
    }
    try:
        out["parsed"] = json.loads(content.strip().strip("`"))
    except Exception:
        out["parsed"] = None

    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        with open(save_to, "w") as f:
            json.dump(out, f, indent=2)
    return out


def test_image(cfg: Config, image_path: Path, save_to: Optional[Path] = None) -> dict:
    if not image_path.exists():
        raise OpenAIError(f"Image not found: {image_path}")
    client = _client(cfg)
    img_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "In one short sentence, does this image look like a satellite or "
                            "aerial photo of a residential property? Reply yes/no with one reason."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                ],
            }
        ],
        max_tokens=80,
        temperature=0,
    )
    out = {
        "model": VISION_MODEL,
        "image_path": str(image_path),
        "response": resp.choices[0].message.content,
        "tokens": {
            "prompt": resp.usage.prompt_tokens if resp.usage else None,
            "completion": resp.usage.completion_tokens if resp.usage else None,
        },
    }
    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        with open(save_to, "w") as f:
            json.dump(out, f, indent=2)
    return out
