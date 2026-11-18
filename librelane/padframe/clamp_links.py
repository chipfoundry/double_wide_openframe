#!/usr/bin/env python3
# Padframe.ClampLinks: join each user domain's vccd and vssd clamp pads.
#
# A sky130_ef_io__{vccd,vssd}_lvc_clamped3_pad has three met3 stubs on its core
# side: two for its own supply and, between them, one for the other rail of the
# clamp (VSSD1 on a vccd pad, VCCD1 on a vssd pad). The wrapper only takes the
# two own-supply stubs (Padframe.BridgePowerPads). The middle stub is a met3
# island that reaches nothing unless the top level wires it, and until it is
# wired the clamp inside the pad has only one of its two terminals.
#
# As in the caravel openframe, the two pads of a domain are joined in metal5:
# two vertical met5 straps per side run in the gap between the pad ring and the
# user area, from one clamp pad to the other, the outer one on vssd<n> and the
# inner one on vccd<n>. Every stub of both pads drops onto the strap of its net
# through a met3 landing, a via3 array, a met4 plate and a via4 array.
# D. Mitch Bailey drew these in the double-wide GDS (lvs-fix-2612). The straps
# here sit where the openframe's own do (mag/chip_io_openframe.mag), measured
# from the pad ring's core-facing edge on each side, 0.7 um from his.
#
# The step runs before global routing so the router sees the straps as fixed
# metal. It fails if a shape comes within minimum spacing of another net's
# fixed metal or would enter the user area.
import os
import sys

from reader import click_odb, click
import odb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from padframe_geom import bloat, cut_array, def_rect, fixed_metal, overlaps, pin_rects  # noqa: E402

WRAPPER_INST = "user_project"
CLAMP3_SUFFIX = "_lvc_clamped3_pad"
CORE_PINS = ("VCCD1", "VSSD1")

STRAP_WIDTH_UM = 4.0
# Strap near edge, measured from the pad ring's core-facing edge: the
# openframe's west straps are at x = 199.59 and 205.19, its east ones at
# 3384.53 and 3378.93 (ring edges 197.965 and 3390.035).
STRAP_OFFSET_UM = {
    # side: (outer strap, vssd<n>; inner strap, vccd<n>)
    "W": (1.625, 7.225),
    "E": (1.505, 7.105),
}
WRAP_CLEAR_UM = 0.3           # inner strap stays this far outside the user area

# Minimum spacing to another net's metal. These shapes are wide (over 3 um),
# so met3 and met4 take the wide-metal spacing (m3.3d, m4.5b), not the 0.3 um
# minimum; met5 is m5.2.
SPACING_UM = {"met3": 0.40, "met4": 0.40, "met5": 1.60}
# Via arrays: cut size, pitch, and margin from the plate edge to the first cut.
VIA3 = dict(name="M3M4_PR", cut=0.20, pitch=0.40, margin=0.10)
VIA4 = dict(name="M4M5_PR", cut=0.80, pitch=1.60, margin=0.40)


@click.command()
@click_odb
def clamp_links(reader):
    block = reader.block
    tech = block.getDataBase().getTech()
    dbu = block.getDbUnitsPerMicron()

    def um(v):
        return int(round(v * dbu))

    def snap(v, grid=5):          # 5 nm manufacturing grid at 1000 dbu/um
        return (v // grid) * grid

    layers = {name: tech.findLayer(name) for name in SPACING_UM}
    via3 = tech.findVia(VIA3["name"])
    via4 = tech.findVia(VIA4["name"])
    if None in layers.values() or via3 is None or via4 is None:
        raise SystemExit("[clamp_links] ERROR: met3..met5 / M3M4_PR / M4M5_PR not in tech")

    die = block.getDieArea()
    wrapper = block.findInst(WRAPPER_INST)
    if wrapper is None:
        raise SystemExit(f"[clamp_links] ERROR: instance {WRAPPER_INST} not found")
    wb = wrapper.getBBox()

    # ---- stubs of every clamped3 pad, per side ------------------------------
    stubs = {"W": [], "E": []}    # (net name, stub rect, clamp instance name)
    ring_edge = {}
    for inst in block.getInsts():
        if not inst.getMaster().getName().endswith(CLAMP3_SUFFIX):
            continue
        bb = inst.getBBox()
        if bb.xMin() == die.xMin():
            side, edge = "W", bb.xMax()
        elif bb.xMax() == die.xMax():
            side, edge = "E", bb.xMin()
        else:
            raise SystemExit(
                f"[clamp_links] ERROR: {inst.getName()} is not on the west or "
                "east edge; only those are handled")
        if ring_edge.setdefault(side, edge) != edge:
            raise SystemExit(f"[clamp_links] ERROR: {side} clamp pads are not aligned")
        for it in inst.getITerms():
            if it.getMTerm().getName() not in CORE_PINS:
                continue
            net = it.getNet()
            if net is None:
                raise SystemExit(
                    f"[clamp_links] ERROR: {inst.getName()}/"
                    f"{it.getMTerm().getName()} has no net")
            for r in pin_rects(it).get("met3", []):
                stubs[side].append((net.getName(), r, inst.getName()))

    width = um(STRAP_WIDTH_UM)
    shapes = []       # (net, layer, rect)
    via_pts = []      # (net, tech via, x, y)
    report = []
    for side, items in stubs.items():
        if not items:
            continue
        nets = sorted({n for n, _, _ in items})
        vss = [n for n in nets if n.startswith("vssd")]
        vcc = [n for n in nets if n.startswith("vccd")]
        if len(nets) != 2 or len(vss) != 1 or len(vcc) != 1:
            raise SystemExit(
                f"[clamp_links] ERROR: {side} clamped3 pads carry {nets}; expected "
                "one vccd<n> and one vssd<n>")
        clamps = sorted({c for _, _, c in items})
        if len(clamps) != 2:
            raise SystemExit(
                f"[clamp_links] ERROR: {side} has clamped3 pads {clamps}; expected two")
        edge = ring_edge[side]
        y0 = min(r[1] for _, r, _ in items)
        y1 = max(r[3] for _, r, _ in items)
        strap = {}
        outer, inner_off = STRAP_OFFSET_UM[side]
        for net, off in ((vss[0], outer), (vcc[0], inner_off)):
            if side == "W":
                strap[net] = (edge + um(off), y0, edge + um(off) + width, y1)
            else:
                strap[net] = (edge - um(off) - width, y0, edge - um(off), y1)
        inner = strap[vcc[0]]
        gap = (wb.xMin() - inner[2]) if side == "W" else (inner[0] - wb.xMax())
        if gap < um(WRAP_CLEAR_UM):
            raise SystemExit(
                f"[clamp_links] ERROR: {side} inner strap is {gap / dbu:.3f} um "
                f"from the user area; needs {WRAP_CLEAR_UM} um")
        for net, r in strap.items():
            shapes.append((net, "met5", def_rect(r)))

        for net, stub, clamp in items:
            s = strap[net]
            # met3 from where the stub leaves the pad cell to the far edge of
            # its strap; the stub itself already covers part or all of it.
            if side == "W":
                land = (max(stub[0], edge), stub[1], max(stub[2], s[2]), stub[3])
                plate = (max(s[0], land[0]), stub[1], s[2], stub[3])
            else:
                land = (min(stub[0], s[0]), stub[1], min(stub[2], edge), stub[3])
                plate = (s[0], stub[1], min(s[2], land[2]), stub[3])
            if plate[2] - plate[0] < um(VIA4["cut"] + 2 * VIA4["margin"]):
                raise SystemExit(
                    f"[clamp_links] ERROR: {clamp} {net} stub leaves only "
                    f"{(plate[2] - plate[0]) / dbu:.3f} um under its strap")
            land, plate = def_rect(land), def_rect(plate)
            shapes.append((net, "met3", land))
            shapes.append((net, "met4", plate))
            for via, spec in ((via3, VIA3), (via4, VIA4)):
                xs = cut_array(plate[0], plate[2], um(spec["cut"]),
                            um(spec["pitch"]), um(spec["margin"]))
                ys = cut_array(plate[1], plate[3], um(spec["cut"]),
                            um(spec["pitch"]), um(spec["margin"]))
                for x in xs:
                    for y in ys:
                        via_pts.append((net, via, snap(x), snap(y)))
        report.append(
            f"{side}: {vss[0]} at x={strap[vss[0]][0] / dbu:.3f}, "
            f"{vcc[0]} at x={strap[vcc[0]][0] / dbu:.3f}, "
            f"y={y0 / dbu:.3f}..{y1 / dbu:.3f}, {len(items)} stubs of "
            f"{', '.join(clamps)}")

    if not shapes:
        raise SystemExit("[clamp_links] ERROR: no clamped3 pads found")

    # ---- checks ------------------------------------------------------------
    own = {n for n, _, _ in shapes}
    fixed = fixed_metal(block, SPACING_UM, own)
    errors = []
    for net, ly, r in shapes:
        zone = bloat(r, um(SPACING_UM[ly]))
        for fr, fnet, what in fixed[ly]:
            if fnet != net and overlaps(fr, zone):
                errors.append(
                    f"{net} {ly} {[v / dbu for v in r]} is within "
                    f"{SPACING_UM[ly]} um of {what}")
        for onet, oly, o in shapes:
            if onet != net and oly == ly and overlaps(o, zone):
                errors.append(f"{net} and {onet} are too close on {ly}")
        if overlaps(r, (wb.xMin(), wb.yMin(), wb.xMax(), wb.yMax())):
            errors.append(f"{net} {ly} {[v / dbu for v in r]} enters the user area")
    if errors:
        raise SystemExit("[clamp_links] ERROR:\n  " + "\n  ".join(sorted(set(errors))[:20]))

    # ---- draw ----------------------------------------------------------------
    swires = {}
    for net_name in sorted(own):
        net = block.findNet(net_name)
        net.setSpecial()
        swires[net_name] = odb.dbSWire.create(net, "ROUTED")
    for net, ly, r in shapes:
        odb.dbSBox.create(swires[net], layers[ly], *r, "STRIPE")
    for net, via, x, y in via_pts:
        odb.dbSBox.create(swires[net], via, x, y, "STRIPE")
    for line in report:
        print(f"[clamp_links] {line}")
    n3 = sum(1 for _, v, _, _ in via_pts if v.getName() == VIA3["name"])
    print(f"[clamp_links] {n3} via3, {len(via_pts) - n3} via4, "
          f"{STRAP_WIDTH_UM} um met5 straps")


if __name__ == "__main__":
    clamp_links()
