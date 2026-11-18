#!/usr/bin/env python3
"""Dump pin probe points for scripts/check_gds_nets.py (run with openroad -python).

    openroad -python -exit scripts/net_probe_points.py \
        def/double_wide_chip_io.def build/probes.json NET [NET ...]

Reads the padframe DEF with the PDK and repo LEFs and writes, for every
instance pin on one of the named nets, the centre (um) and layer of the pin's
metal rectangles, largest first, and its net. More than one rectangle is given
in case the centre of the largest one is not on metal in the GDS.
"""
import glob
import json
import os
import sys

import odb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDK_ROOT = os.environ.get("PDK_ROOT", os.path.expanduser("~/.ciel"))
PDK = os.environ.get("PDK", "sky130A")
REF = os.path.join(PDK_ROOT, PDK, "libs.ref")
MAX_POINTS = 8


def load(def_path):
    db = odb.dbDatabase.create()
    odb.read_lef(db, f"{REF}/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef")
    lefs = [f"{REF}/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef",
            f"{REF}/sky130_fd_io/lef/sky130_ef_io.lef",
            f"{REF}/sky130_fd_io/lef/sky130_fd_io.lef"]
    lefs += sorted(f for f in glob.glob(os.path.join(ROOT, "lef", "*.lef"))
                   if os.path.basename(f) != "double_wide_chip_io.lef")
    lefs += sorted(glob.glob(os.path.join(ROOT, "ip", "*", "lef", "*.lef")))
    for lef in lefs:
        odb.read_lef(db, lef)
    odb.read_def(db.getTech(), def_path)
    return db.getChip().getBlock()


def main(def_path, out_path, nets):
    block = load(def_path)
    dbu = block.getDbUnitsPerMicron()
    out = []
    for name in nets:
        net = block.findNet(name)
        if net is None:
            sys.exit(f"net {name} not in {def_path}")
        for it in net.getITerms():
            inst = it.getInst()
            xf = inst.getTransform()
            rects = []
            for mp in it.getMTerm().getMPins():
                for b in mp.getGeometry():
                    layer = b.getTechLayer()
                    if layer is None or not layer.getName().startswith("met"):
                        continue
                    p1 = odb.Point(b.xMin(), b.yMin())
                    p2 = odb.Point(b.xMax(), b.yMax())
                    xf.apply(p1)
                    xf.apply(p2)
                    r = (min(p1.x(), p2.x()), min(p1.y(), p2.y()),
                         max(p1.x(), p2.x()), max(p1.y(), p2.y()))
                    rects.append(((r[2] - r[0]) * (r[3] - r[1]), layer.getName(), r))
            if not rects:
                continue
            # largest first; the checker takes the first one that has metal
            rects.sort(key=lambda t: -t[0])
            out.append(dict(
                inst=inst.getName(), master=inst.getMaster().getName(),
                pin=it.getMTerm().getName(), net=name,
                points=[dict(layer=layer, x=(r[0] + r[2]) / 2 / dbu,
                             y=(r[1] + r[3]) / 2 / dbu)
                        for _, layer, r in rects[:MAX_POINTS]]))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {len(out)} probe points on {len(nets)} nets to {out_path}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if len(args) < 3:
        sys.exit(__doc__)
    main(args[0], args[1], args[2:])
