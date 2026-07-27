#!/usr/bin/env python3
"""Fix the mis-placed port labels in gds/xres_buf.gds.

The xres_buf cell was mirrored left<->right (about x = 10 um, the centre of its
20 um-wide prBoundary), but the six TOP-LEVEL port labels were left at their
original positions, so every port label ended up on the wrong strap:

    A, X            on layer 69/5  (met2.label)
    VPWR, VGND,
    LVPWR, LVGND    on layer 71/5  (met4.label)

The internal std-cell labels live inside the (correctly mirrored) child cell
instances and are already right, so we only mirror the top-level port labels:

    x -> (2 * 10.0 um) - x     (y and text unchanged)

A one-time backup is written to gds/xres_buf.gds.preflip_bak.
"""
import os
import sys

sys.path.insert(0, "/usr/lib/klayout/pymod")
import klayout.db as db  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDS = os.path.join(ROOT, "gds", "xres_buf.gds")
BAK = GDS + ".preflip_bak"
MIRROR_AXIS_UM = 10.0                 # centre of the 20 um-wide prBoundary
LABEL_LAYERS = [(69, 5), (71, 5)]     # met2.label, met4.label (port labels)


def main():
    if not os.path.exists(BAK):
        with open(GDS, "rb") as src, open(BAK, "wb") as dst:
            dst.write(src.read())
        print(f"backup -> {os.path.relpath(BAK, ROOT)}")

    ly = db.Layout()
    ly.read(GDS)
    top = ly.top_cells()[0]
    axis = round(MIRROR_AXIS_UM / ly.dbu)

    moved = 0
    for lyr, dt in LABEL_LAYERS:
        li = ly.find_layer(lyr, dt)
        if li is None:
            continue
        shapes = top.shapes(li)
        texts = [s.text.dup() for s in shapes.each() if s.is_text()]
        to_erase = [s for s in shapes.each() if s.is_text()]
        for s in to_erase:
            shapes.erase(s)
        for t in texts:
            new_x = 2 * axis - t.x
            shapes.insert(db.Text(t.string, new_x, t.y))
            print(f"  {t.string:6s} {lyr}/{dt}: x {t.x * ly.dbu:.3f} "
                  f"-> {new_x * ly.dbu:.3f}  (y {t.y * ly.dbu:.3f})")
            moved += 1

    ly.write(GDS)
    print(f"fixed {moved} top-level port labels in {os.path.relpath(GDS, ROOT)}")


if __name__ == "__main__":
    main()
