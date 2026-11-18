#!/usr/bin/env python3
"""Replace a macro's blanket LEF obstructions with its real metal, per layer.

    python3 scripts/exact_macro_obs.py constant_block met2 met3

Magic's `lef write -hide` (scripts/gen_macro_lef_def.tcl) covers each layer of a
macro with a few large obstruction rectangles. For constant_block that hides
the fact that its met2 and met3 are a handful of small shapes: the padframe
router then sees a solid wall 0.855 um from the user-area boundary on the east
edge and has no legal way onto the wrapper's loopback pins, although the real
metal leaves a clear lane straight to them.

For each named layer this rewrites the OBS section of lef/<cell>.lef from
gds/<cell>.gds: every drawn shape on the layer, merged, minus the macro's own
pin shapes on that layer, clipped to the macro SIZE, as rectangles. Other
layers and everything outside OBS are left as they are. Needs the klayout
Python module.
"""
import os
import re
import sys

import klayout.db as kdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDS_LAYERS = {"met1": (68, 20), "met2": (69, 20), "met3": (70, 20),
              "met4": (71, 20), "met5": (72, 20)}


def pin_rects(lef_text, layer, dbu):
    """Pin port rectangles of `layer`, in database units."""
    region = kdb.Region()
    for m in re.finditer(r"^  PIN (\S+)\n(.*?)^  END \1\n", lef_text, re.S | re.M):
        cur = None
        for line in m.group(2).splitlines():
            s = line.strip()
            lm = re.match(r"LAYER\s+(\S+)", s)
            if lm:
                cur = lm.group(1)
            rm = re.match(r"RECT\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)", s)
            if rm and cur == layer:
                x1, y1, x2, y2 = (round(float(v) / dbu) for v in rm.groups())
                region.insert(kdb.Box(x1, y1, x2, y2))
    return region


def exact_obs(cell, layers):
    lef_path = os.path.join(ROOT, "lef", f"{cell}.lef")
    lef = open(lef_path).read()
    layout = kdb.Layout()
    layout.read(os.path.join(ROOT, "gds", f"{cell}.gds"))
    top = layout.cell(cell)
    dbu = layout.dbu
    w, h = (float(v) for v in re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", lef).groups())
    box = kdb.Region(kdb.Box(0, 0, round(w / dbu), round(h / dbu)))

    obs = re.search(r"^  OBS\n(.*?)^  END\n", lef, re.S | re.M)
    if not obs:
        sys.exit(f"{lef_path}: no OBS section")
    # split the OBS body into per-layer blocks, keeping their order
    blocks, cur = [], None
    for line in obs.group(1).splitlines():
        lm = re.match(r"\s*LAYER\s+(\S+)\s*;", line)
        if lm:
            cur = [lm.group(1), []]
            blocks.append(cur)
        elif cur is not None:
            cur[1].append(line)

    for layer in layers:
        li = layout.find_layer(*GDS_LAYERS[layer])
        shapes = kdb.Region(top.begin_shapes_rec(li)).merged() if li is not None else kdb.Region()
        region = ((shapes - pin_rects(lef, layer, dbu)) & box).merged()
        rects = []
        for poly in region.decompose_trapezoids_to_region().each():
            if not poly.is_box():
                sys.exit(f"{cell} {layer}: non-rectangular metal, cannot write as RECT")
            b = poly.bbox()
            rects.append(f"        RECT {b.left * dbu:.3f} {b.bottom * dbu:.3f} "
                         f"{b.right * dbu:.3f} {b.top * dbu:.3f} ;")
        for blk in blocks:
            if blk[0] == layer:
                blk[1] = sorted(rects)
                break
        else:
            blocks.append([layer, sorted(rects)])
        print(f"{cell} {layer}: {len(rects)} obstruction rectangles from the GDS")

    body = "".join(f"      LAYER {name} ;\n" + "".join(l + "\n" for l in lines)
                   for name, lines in blocks if lines)
    lef = lef[:obs.start()] + "  OBS\n" + body + "  END\n" + lef[obs.end():]
    with open(lef_path, "w") as f:
        f.write(lef)


if __name__ == "__main__":
    if len(sys.argv) < 3 or any(l not in GDS_LAYERS for l in sys.argv[2:]):
        sys.exit(__doc__)
    exact_obs(sys.argv[1], sys.argv[2:])
