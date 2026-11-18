#!/usr/bin/env python3
# Padframe.UserIdPower: power the user_id_programming block, as in the openframe.
#
# user_id_programming sits in the pad ring's south-east corner, under filler
# slices, with five met5 rails that alternate VPWR / VGND and are not joined
# inside the block. The padframe has no power grid, so nothing reaches them
# unless it is drawn: without this step the block is unpowered and mask_rev
# floats. mag/chip_io_openframe.mag draws the hookup by hand:
#
#   * a met5 finger extends each rail west, out of the block;
#   * two met4 columns cross the fingers, one via4 row per finger: the west
#     column takes the three VPWR rails, the east one the two VGND rails;
#   * from the top of each column a met3 column runs north to the pad ring's
#     own VCCD (west column) or VSSD (east column) rail and lands on it through
#     a via3 array and a met4 pad.
#
# The shapes below are the openframe's, in openframe chip coordinates, moved
# here with the block. The step runs before global routing, so the router
# treats them as fixed metal. It fails if a shape comes within minimum spacing
# of another net's fixed metal, or if either net fails to touch both the block
# pin and a pad-ring rail of its own.
import os
import sys

from reader import click_odb, click
import odb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from padframe_geom import bloat, cut_array, def_rect, fixed_metal, overlaps, pin_rects, touches  # noqa: E402

BLOCK_INST = "user_id_value"
# Block placement in chip_io_openframe.mag: N, lower-left corner here (um).
OPENFRAME_BLOCK_ORIGIN_UM = (3215.77, 46.23)
BLOCK_ORIENT = "R0"

# Minimum spacing to another net's metal. These shapes are wide (over 3 um),
# so met3 and met4 take the wide-metal spacing (m3.3d, m4.5b), not the 0.3 um
# minimum; met5 is m5.2.
SPACING_UM = {"met3": 0.40, "met4": 0.40, "met5": 1.60}
VIA3 = dict(name="M3M4_PR", cut=0.20, pitch=0.40, margin=0.10)
VIA4 = dict(name="M4M5_PR", cut=0.80, pitch=1.60, margin=0.25)

FINGER_X_UM = (3201.98, 3221.44)
# The block's met5 rails (gds/user_id_programming): 1.6 um wide, first one this
# far above the block's lower edge, then every RAIL_PITCH_UM, VPWR first. Its
# LEF only names the first two as pins and covers the other three with one
# met5 obstruction, so each finger is checked against this instead.
RAIL_Y0_UM = 8.48
RAIL_WIDTH_UM = 1.60
RAIL_PITCH_UM = 4.08
RAIL_PINS = ("VPWR", "VGND", "VPWR", "VGND", "VPWR")
# block pin -> shapes, openframe chip coordinates (um)
HOOKUP = {
    "VPWR": dict(
        fingers_y=[(54.71, 56.31), (62.87, 64.47), (71.03, 72.63)],
        via4=[(3202.60, 54.83, 3207.39, 56.19), (3202.54, 63.04, 3207.33, 64.34),
              (3202.59, 71.15, 3207.38, 72.48)],
        met4=[(3202.43, 54.22, 3207.51, 83.08), (3202.54, 186.64, 3207.47, 190.85)],
        via3=[(3202.71, 78.55, 3207.22, 82.85), (3202.89, 186.90, 3207.18, 190.59)],
        met3=[(3202.48, 78.29, 3207.53, 190.845)],
    ),
    "VGND": dict(
        fingers_y=[(58.79, 60.39), (66.95, 68.55)],
        via4=[(3210.55, 58.91, 3215.34, 60.25), (3210.62, 67.07, 3215.41, 68.38)],
        met4=[(3210.45, 54.22, 3215.53, 83.11), (3210.50, 154.06, 3215.48, 158.15)],
        via3=[(3210.73, 78.53, 3215.24, 82.83), (3210.76, 154.22, 3215.30, 157.92)],
        met3=[(3210.49, 78.29, 3215.54, 158.22)],
    ),
}


@click.command()
@click_odb
def user_id_power(reader):
    block = reader.block
    tech = block.getDataBase().getTech()
    dbu = block.getDbUnitsPerMicron()

    def um(v):
        return int(round(v * dbu))

    def snap(v, grid=5):
        return (v // grid) * grid

    layers = {name: tech.findLayer(name) for name in SPACING_UM}
    via3 = tech.findVia(VIA3["name"])
    via4 = tech.findVia(VIA4["name"])
    if None in layers.values() or via3 is None or via4 is None:
        raise SystemExit("[user_id_power] ERROR: met3..met5 / M3M4_PR / M4M5_PR not in tech")

    inst = block.findInst(BLOCK_INST)
    if inst is None:
        raise SystemExit(f"[user_id_power] ERROR: instance {BLOCK_INST} not found")
    if inst.getOrient() != BLOCK_ORIENT:
        raise SystemExit(
            f"[user_id_power] ERROR: {BLOCK_INST} is {inst.getOrient()}, the "
            f"openframe hookup is for {BLOCK_ORIENT}")
    bb = inst.getBBox()
    dx = bb.xMin() - um(OPENFRAME_BLOCK_ORIGIN_UM[0])
    dy = bb.yMin() - um(OPENFRAME_BLOCK_ORIGIN_UM[1])

    def here(r):
        return def_rect((um(r[0]) + dx, um(r[1]) + dy, um(r[2]) + dx, um(r[3]) + dy))

    nets = {}
    for it in inst.getITerms():
        if it.getMTerm().getName() in HOOKUP:
            if it.getNet() is None:
                raise SystemExit(
                    f"[user_id_power] ERROR: {BLOCK_INST}/"
                    f"{it.getMTerm().getName()} has no net")
            nets[it.getMTerm().getName()] = (it.getNet(), it)
    if set(nets) != set(HOOKUP):
        raise SystemExit(f"[user_id_power] ERROR: {BLOCK_INST} lacks {sorted(set(HOOKUP) - set(nets))}")

    rails = {bb.yMin() + um(RAIL_Y0_UM + k * RAIL_PITCH_UM): pin
             for k, pin in enumerate(RAIL_PINS)}
    shapes = []     # (net name, layer, rect)
    via_pts = []    # (net name, tech via, x, y)
    fingers = set()
    for pin, h in HOOKUP.items():
        name = nets[pin][0].getName()
        for y0, y1 in h["fingers_y"]:
            r = here((FINGER_X_UM[0], y0, FINGER_X_UM[1], y1))
            if rails.get(r[1]) != pin or r[3] - r[1] != um(RAIL_WIDTH_UM):
                raise SystemExit(
                    f"[user_id_power] ERROR: finger at y={r[1] / dbu:.3f} is not "
                    f"on a {pin} rail of {BLOCK_INST}")
            shapes.append((name, "met5", r))
            fingers.add(r)
        for ly in ("met4", "met3"):
            for r in h[ly]:
                shapes.append((name, ly, here(r)))
        for via, spec, key in ((via3, VIA3, "via3"), (via4, VIA4, "via4")):
            for r in h[key]:
                x0, y0, x1, y1 = here(r)
                for x in cut_array(x0, x1, um(spec["cut"]), um(spec["pitch"]), um(spec["margin"])):
                    for y in cut_array(y0, y1, um(spec["cut"]), um(spec["pitch"]), um(spec["margin"])):
                        via_pts.append((name, via, snap(x), snap(y)))

    # ---- checks ------------------------------------------------------------
    own = {n for n, _, _ in shapes}
    fixed = fixed_metal(block, SPACING_UM, own)
    errors = []
    for net, ly, r in shapes:
        zone = bloat(r, um(SPACING_UM[ly]))
        for fr, fnet, what in fixed[ly]:
            if r in fingers and what == f"{BLOCK_INST}:OBS":
                continue    # the block's own rails; see RAIL_PINS
            if fnet != net and overlaps(fr, zone):
                errors.append(
                    f"{net} {ly} {[v / dbu for v in r]} is within "
                    f"{SPACING_UM[ly]} um of {what}")
        for onet, oly, o in shapes:
            if onet != net and oly == ly and overlaps(o, zone):
                errors.append(f"{net} and {onet} are too close on {ly}")
    for pin, (net, it) in nets.items():
        name = net.getName()
        mine = [(ly, r) for n, ly, r in shapes if n == name]
        pr = pin_rects(it)
        if not any(touches(r, p) for ly, r in mine for p in pr.get(ly, [])):
            errors.append(f"{name}: no metal on {BLOCK_INST}/{pin}")
        # a pad-ring rail of this net under one of the met4 landing pads
        rails = [fr for fr, fnet, what in fixed["met4"]
                 if fnet == name and not what.startswith(BLOCK_INST + "/")]
        if not any(overlaps(r, fr) for ly, r in mine if ly == "met4" for fr in rails):
            errors.append(f"{name}: the met4 landing is not on a pad-ring {name} rail")
    if errors:
        raise SystemExit("[user_id_power] ERROR:\n  " + "\n  ".join(sorted(set(errors))[:20]))

    # ---- draw ----------------------------------------------------------------
    swires = {}
    for name in sorted(own):
        net = block.findNet(name)
        net.setSpecial()
        swires[name] = odb.dbSWire.create(net, "ROUTED")
    for net, ly, r in shapes:
        odb.dbSBox.create(swires[net], layers[ly], *r, "STRIPE")
    for net, via, x, y in via_pts:
        odb.dbSBox.create(swires[net], via, x, y, "STRIPE")
    n3 = sum(1 for _, v, _, _ in via_pts if v.getName() == VIA3["name"])
    for pin, (net, _) in nets.items():
        print(f"[user_id_power] {BLOCK_INST}/{pin} -> pad-ring {net.getName()} rail, "
              f"{len(HOOKUP[pin]['fingers_y'])} met5 rails")
    print(f"[user_id_power] {n3} via3, {len(via_pts) - n3} via4; block offset from "
          f"the openframe: dx={dx / dbu:.3f} um, dy={dy / dbu:.3f} um")


if __name__ == "__main__":
    user_id_power()
