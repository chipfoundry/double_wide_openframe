#!/usr/bin/env python3
"""Rewrite wrapper LEF power/ground PIN blocks from the final DEF.

Magic.WriteLEF collapses multi-PORT power pins (keeps one met3 rect, drops the
PDN ring ports). The DEF still has every BPin. Rebuild each power PIN in the
LEF from the DEF so padframe routing sees the full clamp-aligned edge ports
plus the met4/met5 ring ports.
"""
from __future__ import annotations

import argparse
import re
import sys

POWER_NETS = {
    "vccd", "vccd1", "vccd2", "vddio", "vdda", "vdda1", "vdda2",
    "vssd", "vssd1", "vssd2", "vssio", "vssa", "vssa1", "vssa2",
}
GND = {
    "vssd", "vssd1", "vssd2", "vssio", "vssa", "vssa1", "vssa2",
}


def _upm(def_text: str) -> int:
    m = re.search(r"UNITS DISTANCE MICRONS (\d+)", def_text)
    if not m:
        raise SystemExit("DEF missing UNITS DISTANCE MICRONS")
    return int(m.group(1))


def _parse_def_power_ports(def_text: str, upm: int):
    """Return {name: [(layer, x1, y1, x2, y2_um), ...]} absolute microns."""
    out = {n: [] for n in POWER_NETS}
    for m in re.finditer(
        r"- (\w+) \+ NET \1 \+ SPECIAL \+ DIRECTION INOUT \+ USE (POWER|GROUND)\n"
        r"(.*?)(?=\n\s*- |\nEND PINS)",
        def_text,
        re.S,
    ):
        name, body = m.group(1), m.group(3)
        if name not in POWER_NETS:
            continue
        # Each + PORT ... until next + PORT or end
        for port in re.finditer(
            r"\+ PORT\n(.*?)(?=\n\s*\+ PORT|\Z)",
            body,
            re.S,
        ):
            pbody = port.group(1)
            placed = re.search(r"\+ FIXED \( ([-\d]+) ([-\d]+) \) \w+", pbody)
            if placed:
                px, py = int(placed.group(1)), int(placed.group(2))
            else:
                px = py = 0
            for box in re.finditer(
                r"\+ LAYER (\w+) \( ([-\d]+) ([-\d]+) \) \( ([-\d]+) ([-\d]+) \)",
                pbody,
            ):
                layer = box.group(1)
                dx1, dy1, dx2, dy2 = map(int, box.groups()[1:])
                x1 = (px + dx1) / upm
                y1 = (py + dy1) / upm
                x2 = (px + dx2) / upm
                y2 = (py + dy2) / upm
                out[name].append((layer, x1, y1, x2, y2))
    return out


def _lef_pin_block(name: str, ports) -> str:
    use = "GROUND" if name in GND else "POWER"
    lines = [
        f"  PIN {name}",
        "    DIRECTION INOUT ;",
        f"    USE {use} ;",
    ]
    for layer, x1, y1, x2, y2 in ports:
        lines.append("    PORT")
        lines.append(f"      LAYER {layer} ;")
        lines.append(
            f"        RECT {x1:.3f} {y1:.3f} {x2:.3f} {y2:.3f} ;"
        )
        lines.append("    END")
    lines.append(f"  END {name}")
    return "\n".join(lines)


def patch_lef(lef_path: str, def_path: str) -> None:
    def_text = open(def_path).read()
    lef_text = open(lef_path).read()
    upm = _upm(def_text)
    ports = _parse_def_power_ports(def_text, upm)
    missing = [n for n, p in ports.items() if not p]
    if missing:
        print(f"[patch_wrapper_lef] WARNING no DEF ports for: {missing}", file=sys.stderr)

    for name, plist in ports.items():
        if not plist:
            continue
        block = _lef_pin_block(name, plist)
        pat = re.compile(rf"  PIN {name}\n.*?  END {name}", re.S)
        if not pat.search(lef_text):
            print(f"[patch_wrapper_lef] WARNING PIN {name} not in LEF", file=sys.stderr)
            continue
        lef_text = pat.sub(block, lef_text, count=1)
        print(f"[patch_wrapper_lef] {name}: {len(plist)} ports")

    with open(lef_path, "w") as f:
        f.write(lef_text)
    print(f"[patch_wrapper_lef] wrote {lef_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lef", required=True)
    ap.add_argument("--def", dest="def_path", required=True)
    args = ap.parse_args()
    patch_lef(args.lef, args.def_path)


if __name__ == "__main__":
    main()
