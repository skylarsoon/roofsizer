"""Single-address pipeline runner.

Usage:
    .venv/bin/python server/run_pipeline.py \
      --address "3561 E 102nd Ct, Thornton, CO 80229" \
      --scenario s_synthesizer \
      --output server/cache
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import certifi as _certifi

for _v in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
    os.environ.setdefault(_v, _certifi.where())

# server/run_pipeline.py — add server/ to path so `import roofer` works
SERVER_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_ROOT))

from roofer.cache import Cache  # noqa: E402
from roofer.config import load_config  # noqa: E402
from roofer.pipeline import run_pipeline  # noqa: E402
from roofer.scenarios import get_scenario  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", required=True)
    parser.add_argument("--scenario", default="s_synthesizer")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--output", default=None,
                        help="output dir (default: server/cache/)")
    args = parser.parse_args()

    cfg = load_config(strict=True)
    scenario = get_scenario(args.scenario)
    cache = Cache(SERVER_ROOT / "cache", refresh=args.refresh_cache)

    output_dir = Path(args.output) if args.output else SERVER_ROOT / "cache"
    output_dir.mkdir(parents=True, exist_ok=True)

    record = {"id": "manual", "address": args.address, "dataset": "manual"}
    res = run_pipeline(
        record=record, scenario=scenario, cfg=cfg, cache=cache,
        output_dir=output_dir, run_id="manual",
    )
    print(json.dumps(res.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
