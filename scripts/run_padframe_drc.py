#!/usr/bin/env python3
"""Run cf-precheck Magic / KLayout DRC against the double-wide padframe GDS."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Prefer workspace cf-precheck fork
_CF_PRECHECK_SRC = Path(__file__).resolve().parents[2] / "cf-precheck" / "src"
if _CF_PRECHECK_SRC.is_dir():
    sys.path.insert(0, str(_CF_PRECHECK_SRC))

from cf_precheck.checks.magic_drc import magic_gds_drc_check  # noqa: E402
from cf_precheck.checks.klayout_drc import klayout_gds_drc_check  # noqa: E402

_SCRIPTS = _CF_PRECHECK_SRC / "cf_precheck" / "drc_scripts"


def _outdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "logs").mkdir(exist_ok=True)
    (path / "outputs" / "reports").mkdir(parents=True, exist_ok=True)
    return path


def run_magic(gds: Path, design: str, pdk: Path, out: Path) -> bool:
    return magic_gds_drc_check(gds, design, pdk, _outdir(out))


def run_klayout(gds: Path, pdk_name: str, out: Path, design: str) -> bool:
    out = _outdir(out)
    checks = [
        ("klayout_feol", _SCRIPTS / f"{pdk_name}_mr.drc", ["-rd", "feol=true"]),
        ("klayout_beol", _SCRIPTS / f"{pdk_name}_mr.drc", ["-rd", "beol=true"]),
        ("klayout_offgrid", _SCRIPTS / f"{pdk_name}_mr.drc", ["-rd", "offgrid=true"]),
        ("klayout_met_min_ca_density", _SCRIPTS / "met_min_ca_density.lydrc", []),
        (
            "klayout_pin_label_purposes_overlapping_drawing",
            _SCRIPTS / "pin_label_purposes_overlapping_drawing.rb.drc",
            ["-rd", f"top_cell_name={design}"],
        ),
        (
            "klayout_zeroarea",
            _SCRIPTS / "zeroarea.rb.drc",
            ["-rd", f"cleaned_output={out / 'outputs' / (gds.stem + '_no_zero_areas.gds')}"],
        ),
    ]
    ok = True
    for name, script, extra in checks:
        if not script.exists():
            print(f"SKIP {name}: missing {script}", file=sys.stderr)
            continue
        print(f"Running {name}...")
        passed = klayout_gds_drc_check(name, script, gds, out, extra)
        print(f"  {'PASS' if passed else 'FAIL'}: {name}")
        ok = ok and passed
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gds", type=Path, required=True)
    ap.add_argument("--design", default="double_wide_chip_io")
    ap.add_argument("--pdk-path", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--mode", choices=("magic", "klayout", "all"), default="all")
    args = ap.parse_args()

    if not args.gds.exists():
        print(f"GDS not found: {args.gds}", file=sys.stderr)
        return 2

    ok = True
    if args.mode in ("magic", "all"):
        print(f"Magic DRC on {args.gds}...")
        magic_ok = run_magic(args.gds, args.design, args.pdk_path, args.out / "magic")
        print(f"  Magic DRC: {'PASS' if magic_ok else 'FAIL'}")
        ok = magic_ok and ok
    if args.mode in ("klayout", "all"):
        ok = run_klayout(args.gds, args.pdk_path.name, args.out / "klayout", args.design) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
