#!/usr/bin/env python3
"""Run cf-precheck LVS against the double-wide padframe."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_CF_PRECHECK_SRC = Path(__file__).resolve().parents[2] / "cf-precheck" / "src"
if _CF_PRECHECK_SRC.is_dir():
    sys.path.insert(0, str(_CF_PRECHECK_SRC))

from cf_precheck.checks.lvs import run_lvs  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--design-dir", type=Path, required=True, help="dw_openframe root")
    ap.add_argument("--pdk-path", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--design", default="double_wide_chip_io")
    args = ap.parse_args()

    config = args.design_dir / f"lvs/{args.design}/lvs_config.json"
    if not config.exists():
        print(f"Missing LVS config: {config}", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    ok = run_lvs(
        args.design_dir,
        args.out,
        args.design,
        config,
        args.pdk_path.parent,
        args.pdk_path.name,
    )
    print("LVS:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
