#!/usr/bin/env python3
"""Dump pin probe points for scripts/check_porb_net.py (run with openroad -python).

    openroad -python -exit scripts/porb_probe_points.py \
        def/double_wide_chip_io.def build/porb_probes.json

Reads the padframe DEF with the PDK and repo LEFs and writes, for every pin that
is on porb_h or must stay off it, the pin's largest metal rectangle (um), its
layer and its netlist net: GPIO pad ENABLE_H / ENABLE_VDDA_H / TIE_HI_ESD /
HLD_H_N, reset pad ENABLE_H / TIE_HI_ESD, and the simple_por and wrapper
porb_h / por_l / porb_l pins.
"""
import json
import os
import sys

import odb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDK_ROOT = os.environ.get("PDK_ROOT", os.path.expanduser("~/.ciel"))
PDK = os.environ.get("PDK", "sky130A")
REF = os.path.join(PDK_ROOT, PDK, "libs.ref")

PINS = {
    "sky130_ef_io__gpiov2_pad": ("ENABLE_H", "ENABLE_VDDA_H", "TIE_HI_ESD", "HLD_H_N"),
    "sky130_fd_io__top_xres4v2": ("ENABLE_H", "TIE_HI_ESD"),
    "simple_por": ("porb_h", "por_l", "porb_l"),
    "double_wide_openframe_project_wrapper": ("porb_h", "por_l", "porb_l"),
}


def main(def_path, out_path):
    db = odb.dbDatabase.create()
    odb.read_lef(db, f"{REF}/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef")
    lefs = [f"{REF}/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef",
            f"{REF}/sky130_fd_io/lef/sky130_ef_io.lef",
            f"{REF}/sky130_fd_io/lef/sky130_fd_io.lef"]
    lefs += [os.path.join(ROOT, "lef", f"{m}.lef") for m in (
        "constant_block", "simple_por", "xres_buf",
        "double_wide_openframe_project_wrapper")]
    lefs += [os.path.join(ROOT, "ip", m, "lef", f"{m}.lef") for m in (
        "dw_openframe_motto", "logo_dw_openframe", "open_source",
        "project_id_textblock", "user_id_programming", "user_id_textblock")]
    for lef in lefs:
        odb.read_lef(db, lef)
    odb.read_def(db.getTech(), def_path)
    block = db.getChip().getBlock()
    dbu = block.getDbUnitsPerMicron()

    out = []
    for inst in block.getInsts():
        master = inst.getMaster().getName()
        if master not in PINS:
            continue
        xf = inst.getTransform()
        for it in inst.getITerms():
            pin = it.getMTerm().getName()
            if pin not in PINS[master]:
                continue
            best = None
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
                    area = (r[2] - r[0]) * (r[3] - r[1])
                    if best is None or area > best[0]:
                        best = (area, layer.getName(), r)
            if best is None:
                continue
            _, layer, r = best
            out.append(dict(
                inst=inst.getName(), master=master, pin=pin, layer=layer,
                net=it.getNet().getName() if it.getNet() else None,
                x=(r[0] + r[2]) / 2 / dbu, y=(r[1] + r[3]) / 2 / dbu,
                rect=[v / dbu for v in r]))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"[porb_probe_points] {len(out)} probe points -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
