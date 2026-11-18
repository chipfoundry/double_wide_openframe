#!/usr/bin/env python3
# Padframe.XresLoops: the reset pad's local wiring, as in the caravel openframe.
#
# Three nets tie control pins of the reset pad (sky130_fd_io__top_xres4v2) to
# tie-offs on the pad itself or to its constant_block. They never leave the
# pad's core-facing edge, the router gets no access points there, and the
# openframe does not route them either: mag/chip_io_openframe.mag draws them by
# hand. Without them six high-voltage control inputs of the reset pad float.
#
#   xres_vss_loop      TIE_LO_ESD -> DISABLE_PULLUP_H, EN_VDDIO_SIG_H, INP_SEL_H,
#                      FILT_IN_H, PULLUP_H. A met1 bar just outside the pad edge
#                      with a via1 (one pin: via1 + via2) down from each pin.
#   xresloop           TIE_WEAK_HI_H -> PAD_A_ESD_H. A met3 bar above the met1
#                      one, with a met3 leg onto each pin.
#   xres_loopback_one  constant_block `one` -> ENABLE_VDDIO. met3 leg on the pad
#                      pin, via2, met2 up to the height of the constant_block
#                      pin, via2, met3 across to it.
#
# The shapes below are the openframe's own (D. Mitch Bailey redrew the same ones
# in the double-wide GDS, lvs-fix-2612), given in openframe chip coordinates and
# moved here with the pad. Only the last leg of xres_loopback_one is computed,
# because this constant_block is not oriented as the openframe's is.
#
# The step runs before global routing, so the router treats the wiring as fixed
# metal. It fails if a shape comes within minimum spacing of another net's fixed
# metal, or if any pin of the three nets is left untouched.
import os
import sys

from reader import click_odb, click
import odb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from padframe_geom import bloat, def_rect, fixed_metal, overlaps, pin_rects, touches  # noqa: E402

PAD_INST = "master_resetb_pad"
CONST_INST = "constant_value_xres_inst"
# Reset pad placement in chip_io_openframe.mag: R180, origin at this point (um).
OPENFRAME_PAD_ORIGIN_UM = (738.0, 200.0)
PAD_ORIENT = "R180"

# Minimum spacing to another net's metal (sky130 m1.2, m2.2, m3.3a).
SPACING_UM = {"met1": 0.14, "met2": 0.14, "met3": 0.30}
VIA_NAMES = ("M1M2_PR", "M2M3_PR", "M2M3_PR_R")

# layer -> rectangles (x0, y0, x1, y1), openframe chip coordinates in um.
RECTS = {
    "xres_vss_loop": {
        "met1": [
            (704.940, 200.365, 723.305, 200.625),   # the bar
            (712.865, 200.000, 713.095, 200.365),   # met1 pin
        ],
        "met2": [
            (704.985, 199.950, 705.245, 200.655),
            (709.935, 199.990, 710.255, 200.655),
            (715.345, 199.980, 715.605, 200.655),
            (716.995, 200.170, 717.645, 200.655),
            (723.020, 199.950, 723.280, 200.655),
        ],
        "met3": [
            (717.015, 199.960, 717.625, 200.485),   # met3 pin
        ],
    },
    "xresloop": {
        "met3": [
            (665.470, 200.790, 720.050, 201.090),   # the bar
            (665.470, 199.920, 665.770, 200.790),
            (719.750, 199.920, 720.050, 200.790),
        ],
    },
    "xres_loopback_one": {
        "met3": [
            (729.160, 199.910, 729.510, 200.740),   # met3 pin
        ],
    },
}
# (tech via, x, y): via centres, openframe chip coordinates.
VIAS = {
    "xres_vss_loop": [
        ("M1M2_PR", 705.110, 200.495),
        ("M1M2_PR", 710.090, 200.495),
        ("M1M2_PR", 715.470, 200.495),
        ("M1M2_PR", 717.315, 200.495),
        ("M1M2_PR", 723.145, 200.495),
        # _R: its met2 landing is 0.28 um tall, as the openframe's contact is.
        # The upright via's 0.37 um would end 0.125 um above the pad's own
        # met2 at the cell edge, a same-net notch under m2.2.
        ("M2M3_PR_R", 717.315, 200.310),
    ],
    "xresloop": [],
    "xres_loopback_one": [
        ("M2M3_PR", 729.335, 200.520),
    ],
}
# xres_loopback_one riser: met2 column on the pad pin's via, openframe x range.
ONE_RISER_X_UM = (729.145, 729.535)
ONE_RISER_Y0_UM = 200.370
ONE_VIA_X_UM = 729.295        # upper via2, on the riser
ONE_BAR_HALF_UM = 0.165       # met3 bar half-width (0.33 um wide)
ONE_PIN_OVERLAP_UM = 0.185    # how far the bar runs onto the constant_block pin


@click.command()
@click_odb
def xres_loops(reader):
    block = reader.block
    tech = block.getDataBase().getTech()
    dbu = block.getDbUnitsPerMicron()

    def um(v):
        return int(round(v * dbu))

    layers = {name: tech.findLayer(name) for name in SPACING_UM}
    vias = {name: tech.findVia(name) for name in VIA_NAMES}
    if None in layers.values() or None in vias.values():
        raise SystemExit("[xres_loops] ERROR: met1..met3 / M1M2_PR / M2M3_PR(_R) not in tech")

    pad = block.findInst(PAD_INST)
    const = block.findInst(CONST_INST)
    if pad is None or const is None:
        raise SystemExit(f"[xres_loops] ERROR: {PAD_INST} or {CONST_INST} not found")
    if pad.getOrient() != PAD_ORIENT:
        raise SystemExit(
            f"[xres_loops] ERROR: {PAD_INST} is {pad.getOrient()}, the openframe "
            f"wiring is for {PAD_ORIENT}")
    # R180 puts the instance origin at the upper-right corner of its bounding box.
    bbox = pad.getBBox()
    dx = bbox.xMax() - um(OPENFRAME_PAD_ORIGIN_UM[0])
    dy = bbox.yMax() - um(OPENFRAME_PAD_ORIGIN_UM[1])

    def here(r):
        return def_rect((um(r[0]) + dx, um(r[1]) + dy, um(r[2]) + dx, um(r[3]) + dy))

    # ---- collect shapes per net -------------------------------------------
    rects = {n: {ly: [here(r) for r in rs] for ly, rs in by.items()}
             for n, by in RECTS.items()}
    via_pts = {n: [(name, um(x) + dx, um(y) + dy) for name, x, y in vs]
               for n, vs in VIAS.items()}

    # xres_loopback_one: riser and bar up to the constant_block `one` pin.
    one_net = block.findNet("xres_loopback_one")
    if one_net is None:
        raise SystemExit("[xres_loops] ERROR: net xres_loopback_one not found")
    one_pins = [it for it in one_net.getITerms()
                if it.getInst().getName() == CONST_INST]
    if len(one_pins) != 1:
        raise SystemExit(
            f"[xres_loops] ERROR: expected one {CONST_INST} pin on xres_loopback_one")
    cb = pin_rects(one_pins[0]).get("met3")
    if not cb:
        raise SystemExit(f"[xres_loops] ERROR: {CONST_INST}/one has no met3")
    cb = min(cb, key=lambda r: r[0])           # the pin shape facing the pad
    yc = (cb[1] + cb[3]) // 2
    half = um(ONE_BAR_HALF_UM)
    rx0, rx1 = um(ONE_RISER_X_UM[0]) + dx, um(ONE_RISER_X_UM[1]) + dx
    if not rx1 < cb[0]:
        raise SystemExit(f"[xres_loops] ERROR: {CONST_INST}/one is not east of the riser")
    if not (cb[1] <= yc - half and yc + half <= cb[3]):
        half = (cb[3] - cb[1]) // 2            # keep the bar within the pin
    one = rects["xres_loopback_one"]
    one.setdefault("met2", []).append(def_rect(
        (rx0, um(ONE_RISER_Y0_UM) + dy, rx1, yc + half + um(0.02))))
    one["met3"].append(def_rect(
        (rx0 - um(0.015), yc - half, min(cb[0] + um(ONE_PIN_OVERLAP_UM), cb[2]),
         yc + half)))
    via_pts["xres_loopback_one"].append(("M2M3_PR", um(ONE_VIA_X_UM) + dx, yc))

    # Via enclosures count as metal of their net too.
    def via_metal(name, x, y):
        out = []
        for box in vias[name].getBoxes():
            layer = box.getTechLayer()
            if layer is not None and layer.getName() in SPACING_UM:
                out.append((layer.getName(), (x + box.xMin(), y + box.yMin(),
                                              x + box.xMax(), y + box.yMax())))
        return out

    metal = {n: {ly: list(rs) for ly, rs in by.items()} for n, by in rects.items()}
    for n, vs in via_pts.items():
        for name, x, y in vs:
            for ly, r in via_metal(name, x, y):
                metal[n].setdefault(ly, []).append(r)

    # ---- checks ------------------------------------------------------------
    fixed = fixed_metal(block, SPACING_UM, set(RECTS))
    errors = []
    for n, by in metal.items():
        for ly, rs in by.items():
            clear = um(SPACING_UM[ly])
            for r in rs:
                zone = bloat(r, clear)
                for fr, fnet, what in fixed[ly]:
                    if fnet != n and overlaps(fr, zone):
                        errors.append(
                            f"{n} {ly} {[v / dbu for v in r]} is within "
                            f"{SPACING_UM[ly]} um of {what}")
        # the three nets against each other
        for m, other in metal.items():
            if m <= n:
                continue
            for ly, rs in by.items():
                clear = um(SPACING_UM[ly])
                for r in rs:
                    for o in other.get(ly, []):
                        if overlaps(o, bloat(r, clear)):
                            errors.append(f"{n} and {m} are too close on {ly}")
    reached = {}
    for n, by in metal.items():
        net = block.findNet(n)
        if net is None:
            errors.append(f"net {n} not found")
            continue
        local = (PAD_INST, CONST_INST)
        pins = [it for it in net.getITerms() if it.getInst().getName() in local]
        others = [it for it in net.getITerms()
                  if it.getInst().getName() not in local]
        if others:
            errors.append(
                f"{n} also reaches "
                f"{[i.getInst().getName() + '/' + i.getMTerm().getName() for i in others]}")
        for it in pins:
            pr = pin_rects(it)
            if not any(touches(r, p) for ly, rs in by.items()
                       for r in rs for p in pr.get(ly, [])):
                errors.append(
                    f"{n}: no metal on {it.getInst().getName()}/"
                    f"{it.getMTerm().getName()}")
        reached[n] = len(pins)
    if errors:
        raise SystemExit("[xres_loops] ERROR:\n  " + "\n  ".join(sorted(set(errors))))

    # ---- draw ----------------------------------------------------------------
    for n in RECTS:
        net = block.findNet(n)
        net.setSpecial()
        swire = odb.dbSWire.create(net, "ROUTED")
        for ly, rs in rects[n].items():
            for r in rs:
                odb.dbSBox.create(swire, layers[ly], *r, "STRIPE")
        for name, x, y in via_pts[n]:
            odb.dbSBox.create(swire, vias[name], x, y, "STRIPE")
        print(f"[xres_loops] {n}: {reached[n]} pins, "
              f"{sum(len(r) for r in rects[n].values())} shapes, "
              f"{len(via_pts[n])} vias")
    print(f"[xres_loops] reset pad offset from the openframe: "
          f"dx={dx / dbu:.3f} um, dy={dy / dbu:.3f} um")


if __name__ == "__main__":
    xres_loops()
