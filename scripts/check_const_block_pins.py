#!/usr/bin/env python3
"""Check every constant_block's real metal against the wrapper's pins.

    python3 scripts/check_const_block_pins.py [--suggest]

Places gds/constant_block.gds at each instance location in
librelane/padframe/config.yaml and tests its met1..met4 shapes against every
pin shape of librelane/wrapper/pin_template.def on the same layer: an overlap is
a short, anything closer than the layer's minimum spacing a spacing violation.
The wrapper's pins reach 2 um outside the user area, where the per-pad blocks
sit, so a block must be clear of them. Exits non-zero on any conflict.

--suggest also prints, per edge, the along-edge shifts (relative to the current
placement, within +-3 um) that clear every pin for every block on that edge.
Needs the klayout Python module and PyYAML.
"""
import collections
import os
import re
import sys

import klayout.db as kdb
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRAP_OFF = 210685                       # wrapper origin in the die, nm
SPACING = {"met1": 140, "met2": 140, "met3": 300, "met4": 300}
GDS_LAYERS = {"met1": (68, 20), "met2": (69, 20), "met3": (70, 20), "met4": (71, 20)}
ORIENT = {"N": kdb.Trans.R0, "S": kdb.Trans.R180, "W": kdb.Trans.R90, "E": kdb.Trans.R270}
SIZE = (14000, 13000)                   # constant_block LEF SIZE, nm


def placed(orient, x, y):
    """Transform that puts the block's LEF box lower-left corner at (x, y)."""
    t = kdb.Trans(ORIENT[orient])
    bb = kdb.Box(0, 0, *SIZE).transformed(t)
    return kdb.Trans(t.rot, t.is_mirror(), x - bb.left, y - bb.bottom)


def main():
    suggest = "--suggest" in sys.argv[1:]
    cfg = yaml.safe_load(open(os.path.join(ROOT, "librelane/padframe/config.yaml")))
    insts = cfg["MACROS"]["constant_block"]["instances"]
    layout = kdb.Layout()
    layout.read(os.path.join(ROOT, "gds/constant_block.gds"))
    top = layout.top_cell()
    shapes = {ly: kdb.Region(top.begin_shapes_rec(layout.find_layer(*GDS_LAYERS[ly]))).merged()
              for ly in SPACING}

    pins = collections.defaultdict(list)   # layer -> [(name, box)]
    text = open(os.path.join(ROOT, "librelane/wrapper/pin_template.def")).read()
    name = None
    for line in text.splitlines():
        m = re.match(r"- (\S+) \+ NET", line)
        if m:
            name = m.group(1)
        b = re.search(r"\+ LAYER (\w+) \( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \)", line)
        if b and name:
            x1, y1, x2, y2 = (int(v) + WRAP_OFF for v in b.groups()[1:])
            pins[b.group(1)].append((name, kdb.Box(x1, y1, x2, y2)))
    pin_region = {ly: kdb.Region([b for _, b in pins[ly]]) for ly in SPACING}

    def conflicts(tr):
        out = []
        for ly, sp in SPACING.items():
            if not pins[ly]:
                continue
            metal = shapes[ly].transformed(tr)
            zone = metal.sized(sp - 1)
            if (zone & pin_region[ly]).is_empty():
                continue
            for pname, box in pins[ly]:
                r = kdb.Region(box)
                if not (metal & r).is_empty():
                    out.append(("short", ly, pname))
                elif not (zone & r).is_empty():
                    out.append(("spacing", ly, pname))
        return out

    found = []
    by_side = collections.defaultdict(list)
    for iname, v in insts.items():
        x, y = (round(c * 1000) for c in v["location"])
        m = re.match(r"gpio_([nsew])", iname)
        by_side[m.group(1).upper() if m else "-"].append((iname, v["orientation"], x, y))
        for kind, ly, pname in conflicts(placed(v["orientation"], x, y)):
            found.append(f"{kind:8s} {ly} {iname} <-> {pname}")
    print(f"{len(insts)} constant blocks, {sum(len(p) for p in pins.values())} pin shapes: "
          f"{len(found)} conflicts")
    for line in found[:12]:
        print("  " + line)

    if suggest:
        step = 5
        for side in "ENWS":
            ok = None
            for iname, orient, x, y in by_side[side]:
                good = set()
                for d in range(-3000, 3001, step):
                    dx, dy = (d, 0) if side in "NS" else (0, d)
                    if not conflicts(placed(orient, x + dx, y + dy)):
                        good.add(d)
                ok = good if ok is None else ok & good
            runs = []
            for d in sorted(ok or []):
                if runs and d - runs[-1][1] == step:
                    runs[-1][1] = d
                else:
                    runs.append([d, d])
            print(f"  {side}: clear for shifts (um) "
                  + (", ".join(f"{a / 1000:+.3f}..{b / 1000:+.3f}" for a, b in runs) or "none"))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
