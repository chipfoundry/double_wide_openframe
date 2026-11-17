#!/usr/bin/env python3
# Padframe.PorbRing: hand-drawn porb_h distribution, as in the caravel openframe.
#
# The openframe drives ENABLE_H / ENABLE_VDDA_H of every GPIO pad, and ENABLE_H
# of the resetb (xres4v2) pad, from the power-on reset porb_h. Its layout does
# not rely on the router for this: mag/chip_io_openframe.mag carries one closed
# met1 loop, 0.26 um wide, around the user area at 209.33 um from the die edge,
# a short stub from simple_por's porb_h, and per pad a via1 on the loop plus a
# met2 stub to each enable pin (chip_io_gpio_connects_{horiz,vert}).
#
# This step rebuilds exactly that in the double-wide padframe, before global
# routing, as SPECIAL wiring on porb_h (Padframe.ResetSpecialNets already marks
# porb_h SPECIAL, so TritonRoute leaves the net alone and routes around it):
#
#   * Loop: four met1 stripes forming a closed rectangle. Each side sits at the
#     openframe offset (LOOP_OFFSET_UM) unless a fixed met1 shape (pad pin/OBS,
#     constant_block, clamp...) is too close, in which case that side moves
#     inward just far enough to clear it. It must still stay WRAP_CLEAR_UM
#     outside the user wrapper boundary, otherwise the step fails.
#   * Pad taps: for every porb_h pin on a GPIO or reset pad, a met2 stub the
#     width of the pin, from the pin straight in to the loop, plus one via1
#     (sky130 M1M2_PR / M1M2_PR_R) on the loop.
#   * POR tap: simple_por.gds already carries porb_h out of the macro to the
#     wrapper pin (met2 "collar", with a met1 end piece joined by 4 via1 cuts).
#     That met1 end lies on the west loop at the openframe offset; a met1 patch
#     over it and across the loop makes the joint explicit.
#
# Every shape drawn here is checked against the fixed met1/met2 geometry already
# in the design (instance pins and obstructions, other nets' special wires);
# any spacing conflict aborts the step instead of producing a short.
from reader import click_odb, click
import odb

NET = "porb_h"
WRAPPER_INST = "user_project"
POR_INST = "por"

LOOP_WIDTH_UM = 0.26     # openframe loop width
LOOP_OFFSET_UM = 209.33  # openframe: loop outer edge, measured from the die edge
MET1_CLEAR_UM = 0.20     # loop <-> foreign fixed met1 (m1.2 spacing is 0.14)
MET2_CLEAR_UM = 0.20     # stub <-> foreign fixed met2 (m2.2 spacing is 0.14)
WRAP_CLEAR_UM = 0.30     # loop inner edge stays this far outside the wrapper

# Pad masters and the enable pins that ride on porb_h (chip_io_openframe.v).
ENABLE_PINS = {
    "sky130_ef_io__gpiov2_pad": ("ENABLE_H", "ENABLE_VDDA_H"),
    "sky130_fd_io__top_xres4v2": ("ENABLE_H",),
}

# simple_por.gds (repo gds/) porb_h collar met1 end piece, macro-local um.
# GDS-only geometry: the simple_por LEF abstract does not describe the collar.
POR_COLLAR_MET1_UM = (59.55, 151.635, 59.83, 154.2)

SIDES = "WESN"


def _xform_rect(xf, box):
    p1 = odb.Point(box.xMin(), box.yMin())
    p2 = odb.Point(box.xMax(), box.yMax())
    xf.apply(p1)
    xf.apply(p2)
    return (min(p1.x(), p2.x()), min(p1.y(), p2.y()),
            max(p1.x(), p2.x()), max(p1.y(), p2.y()))


def _bloat(r, d):
    return (r[0] - d, r[1] - d, r[2] + d, r[3] + d)


def _overlaps(a, b):
    # strict overlap (touching edges do not count)
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class Geometry:
    """Fixed met1/met2 shapes of everything except the wrapper and porb_h."""

    def __init__(self, block, layers):
        self.shapes = {name: [] for name in layers}  # layer -> [(rect, what)]
        for inst in block.getInsts():
            if inst.getName() == WRAPPER_INST:
                # The wrapper is the user area; the loop is kept outside it by
                # WRAP_CLEAR_UM. Its edge pins (met2/met3) are checked below.
                self._add_wrapper_pins(inst)
                continue
            xf = inst.getTransform()
            master = inst.getMaster()
            for it in inst.getITerms():
                net = it.getNet()
                if net is not None and net.getName() == NET:
                    continue  # same net: overlap is a connection, not a short
                mterm = it.getMTerm()
                for mpin in mterm.getMPins():
                    for box in mpin.getGeometry():
                        self._add(box, xf, f"{inst.getName()}/{mterm.getName()}")
            for box in master.getObstructions():
                self._add(box, xf, f"{inst.getName()}:OBS")
        for net in block.getNets():
            if net.getName() == NET:
                continue
            for sw in net.getSWires():
                for box in sw.getWires():
                    if box.isVia():
                        continue
                    layer = box.getTechLayer()
                    if layer is not None and layer.getName() in self.shapes:
                        self.shapes[layer.getName()].append((
                            (box.xMin(), box.yMin(), box.xMax(), box.yMax()),
                            f"{net.getName()}:special",
                        ))

    def _add(self, box, xf, what):
        layer = box.getTechLayer()
        if layer is None or layer.getName() not in self.shapes:
            return
        self.shapes[layer.getName()].append((_xform_rect(xf, box), what))

    def _add_wrapper_pins(self, inst):
        xf = inst.getTransform()
        for it in inst.getITerms():
            net = it.getNet()
            if net is not None and net.getName() == NET:
                continue
            for mpin in it.getMTerm().getMPins():
                for box in mpin.getGeometry():
                    self._add(box, xf, f"{WRAPPER_INST}/{it.getMTerm().getName()}")

    def conflicts(self, layer, rect, clear):
        zone = _bloat(rect, clear)
        return [(r, w) for r, w in self.shapes[layer] if _overlaps(r, zone)]


@click.command()
@click_odb
def porb_ring(reader):
    block = reader.block
    tech = block.getDataBase().getTech()
    dbu = block.getDbUnitsPerMicron()
    met1 = tech.findLayer("met1")
    met2 = tech.findLayer("met2")
    via_ns = tech.findVia("M1M2_PR")    # met1 long in x: horizontal loop
    via_ew = tech.findVia("M1M2_PR_R")  # met1 long in y: vertical loop
    if None in (met1, met2, via_ns, via_ew):
        raise SystemExit("[porb_ring] ERROR: met1/met2/M1M2_PR(_R) not in tech")

    def um(v):
        return int(round(v * dbu))

    net = block.findNet(NET)
    if net is None:
        raise SystemExit(f"[porb_ring] ERROR: net {NET} not found")
    wrapper = block.findInst(WRAPPER_INST)
    if wrapper is None:
        raise SystemExit(f"[porb_ring] ERROR: instance {WRAPPER_INST} not found")

    die = block.getDieArea()
    dx0, dy0, dx1, dy1 = die.xMin(), die.yMin(), die.xMax(), die.yMax()
    wb = wrapper.getBBox()
    wrap_edge = {  # wrapper boundary, as a distance from each die edge
        "W": wb.xMin() - dx0, "E": dx1 - wb.xMax(),
        "S": wb.yMin() - dy0, "N": dy1 - wb.yMax(),
    }
    width = um(LOOP_WIDTH_UM)
    geo = Geometry(block, ("met1", "met2"))

    # ---- loop geometry --------------------------------------------------
    def seg_rect(side, off):
        """Loop stripe for `side` at outer-edge distance off[side]."""
        w, e, s, n = off["W"], off["E"], off["S"], off["N"]
        if side == "W":
            return (dx0 + w, dy0 + s, dx0 + w + width, dy1 - n)
        if side == "E":
            return (dx1 - e - width, dy0 + s, dx1 - e, dy1 - n)
        if side == "S":
            return (dx0 + w, dy0 + s, dx1 - e, dy0 + s + width)
        return (dx0 + w, dy1 - n - width, dx1 - e, dy1 - n)

    def depth_of(side, r):
        """Far edge of rect r as a distance from die edge `side`."""
        return {"W": r[2] - dx0, "E": dx1 - r[0],
                "S": r[3] - dy0, "N": dy1 - r[1]}[side]

    off = {s: um(LOOP_OFFSET_UM) for s in SIDES}
    clear1 = um(MET1_CLEAR_UM)
    for _ in range(20):
        moved = False
        for side in SIDES:
            hits = geo.conflicts("met1", seg_rect(side, off), clear1)
            if hits:
                need = max(depth_of(side, r) for r, _ in hits) + clear1
                if need > off[side]:
                    off[side] = need
                    moved = True
        if not moved:
            break
    for side in SIDES:
        hits = geo.conflicts("met1", seg_rect(side, off), clear1)
        if hits:
            raise SystemExit(
                f"[porb_ring] ERROR: {side} loop still conflicts with "
                f"{[w for _, w in hits[:5]]}")
        limit = wrap_edge[side] - width - um(WRAP_CLEAR_UM)
        if off[side] > limit:
            raise SystemExit(
                f"[porb_ring] ERROR: {side} loop needs offset "
                f"{off[side] / dbu:.3f} um but must stay <= {limit / dbu:.3f} um "
                f"to clear the wrapper by {WRAP_CLEAR_UM} um")

    net.setSpecial()
    swire = odb.dbSWire.create(net, "ROUTED")
    for side in SIDES:
        odb.dbSBox.create(swire, met1, *seg_rect(side, off), "RING")

    # ---- pad taps: met2 stub + via1 per porb_h enable pin -----------------
    clear2 = um(MET2_CLEAR_UM)

    def met2_landing(via):
        for box in via.getBoxes():
            if box.getTechLayer() is not None and box.getTechLayer().getName() == "met2":
                return box.xMin(), box.yMin(), box.xMax(), box.yMax()
        raise SystemExit(f"[porb_ring] ERROR: via {via.getName()} has no met2")

    land_ew = met2_landing(via_ew)  # relative to the via origin
    land_ns = met2_landing(via_ns)
    taps = []
    unexpected = []
    for it in net.getITerms():
        inst = it.getInst()
        master = inst.getMaster().getName()
        pin = it.getMTerm().getName()
        if inst.getName() in (WRAPPER_INST, POR_INST):
            continue
        if pin not in ENABLE_PINS.get(master, ()):
            unexpected.append(f"{inst.getName()}/{pin}")
            continue
        rects = [
            _xform_rect(inst.getTransform(), box)
            for mpin in it.getMTerm().getMPins()
            for box in mpin.getGeometry()
            if box.getTechLayer() is not None
            and box.getTechLayer().getName() == "met2"
        ]
        if not rects:
            raise SystemExit(f"[porb_ring] ERROR: {inst.getName()}/{pin} has no met2")
        pr = (min(r[0] for r in rects), min(r[1] for r in rects),
              max(r[2] for r in rects), max(r[3] for r in rects))
        cx, cy = (pr[0] + pr[2]) // 2, (pr[1] + pr[3]) // 2
        side = min(
            {"W": cx - dx0, "E": dx1 - cx, "S": cy - dy0, "N": dy1 - cy}.items(),
            key=lambda kv: kv[1],
        )[0]
        loop = seg_rect(side, off)
        # The stub covers the whole pin and runs on to the loop centre, where
        # the via's met2 landing (same width as the stub) carries it a little
        # past the loop. Only the metal beyond the pin's core-facing end is new,
        # so that part, up to the far end of the landing, is what gets checked
        # (`check`, trimmed by the clearance so the bloated zone starts exactly
        # at the pin end); metal beside the pin inside the pad cell is the
        # cell's own business.
        if side in "WE":
            lc = (loop[0] + loop[2]) // 2           # loop centre x
            if side == "W":
                stub = (pr[0], pr[1], lc, pr[3])
                check = (pr[2] + clear2, pr[1], lc + land_ew[2], pr[3])
            else:
                stub = (lc, pr[1], pr[2], pr[3])
                check = (lc + land_ew[0], pr[1], pr[0] - clear2, pr[3])
            via, vx, vy = via_ew, lc, cy
        else:
            lc = (loop[1] + loop[3]) // 2           # loop centre y
            if side == "S":
                stub = (pr[0], pr[1], pr[2], lc)
                check = (pr[0], pr[3] + clear2, pr[2], lc + land_ns[3])
            else:
                stub = (pr[0], lc, pr[2], pr[3])
                check = (pr[0], lc + land_ns[1], pr[2], pr[1] - clear2)
            via, vx, vy = via_ns, cx, lc
        if check[2] <= check[0] or check[3] <= check[1]:
            raise SystemExit(
                f"[porb_ring] ERROR: {inst.getName()}/{pin} is not outside the loop")
        hits = geo.conflicts("met2", check, clear2)
        if hits:
            raise SystemExit(
                f"[porb_ring] ERROR: stub for {inst.getName()}/{pin} conflicts "
                f"with {[w for _, w in hits[:5]]}")
        odb.dbSBox.create(swire, met2, *stub, "STRIPE")
        odb.dbSBox.create(swire, via, vx, vy, "STRIPE")
        taps.append((side, inst.getName(), pin))

    if unexpected:
        raise SystemExit(
            f"[porb_ring] ERROR: porb_h reaches pins this step does not tap: "
            f"{unexpected[:8]}")

    # ---- POR tap: simple_por collar met1 end -> west loop -----------------
    por = block.findInst(POR_INST)
    if por is None:
        raise SystemExit(f"[porb_ring] ERROR: instance {POR_INST} not found")
    cx0, cy0, cx1, cy1 = POR_COLLAR_MET1_UM
    collar = _xform_rect(por.getTransform(),
                         odb.Rect(um(cx0), um(cy0), um(cx1), um(cy1)))
    west = seg_rect("W", off)
    if not (collar[1] >= west[1] and collar[3] <= west[3]):
        raise SystemExit("[porb_ring] ERROR: simple_por collar is not beside the west loop")
    patch = (min(collar[0], west[0]), collar[1], max(collar[2], west[2]), collar[3])
    hits = geo.conflicts("met1", patch, clear1)
    if hits:
        raise SystemExit(
            f"[porb_ring] ERROR: POR tap conflicts with {[w for _, w in hits[:5]]}")
    odb.dbSBox.create(swire, met1, *patch, "STRIPE")

    # ---- report -----------------------------------------------------------
    perim = 2 * ((dx1 - dx0 - off["W"] - off["E"]) + (dy1 - dy0 - off["S"] - off["N"]))
    per_side = {s: sum(1 for t in taps if t[0] == s) for s in SIDES}
    print("[porb_ring] loop outer edge from die edge (um): " + ", ".join(
        f"{s}={off[s] / dbu:.3f}" for s in SIDES))
    print("[porb_ring] wrapper clearance (um): " + ", ".join(
        f"{s}={(wrap_edge[s] - off[s] - width) / dbu:.3f}" for s in SIDES))
    print(f"[porb_ring] loop length {perim / dbu / 1000:.2f} mm, width {LOOP_WIDTH_UM} um")
    print(f"[porb_ring] {len(taps)} pad taps (per side {per_side}); "
          f"POR tap at y={collar[1] / dbu:.3f}..{collar[3] / dbu:.3f} um")


if __name__ == "__main__":
    porb_ring()
