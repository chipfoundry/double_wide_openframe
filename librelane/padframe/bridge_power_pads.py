#!/usr/bin/env python3
# Bridge each power/ground clamp pad's core-facing met3 stubs to the wrapper.
#
# Power nets are SPECIAL (VDD_NETS/GND_NETS), so TritonRoute will not route them
# the way it bridges GPIO signals. Draw a same-net met3 special stripe from
# every clamp domain-pin met3 rectangle to the facing edge of `user_project`,
# matching the stub width (~24um) -- the openframe dual-stub pattern.
#
# Straps are attributed to the clamp's *package* net (clamp_vdda1_0 -> vdda1)
# so they land on the matching wrapper edge PORT. For HVC analog clamps the
# met3 stubs live on the abutment pin (VDDA/VSSA). That pin is the pad ring's
# analog rail, which the disconnect slices cut into one segment per domain, and
# an analog clamp always sits in its own domain's segment (the pad generator
# checks this), so the stub is on the package net too.
#
# A clamped3 pad has three stubs: its own supply twice (VCCD1 on a vccd pad) and
# between them the other rail of its clamp (VSSD1). As in the openframe, the
# wrapper has a port for each, so all three are strapped, each on the net its
# pin carries. Padframe.ClampLinks also joins the domain's two pads in met5.
#
# A strap is written to DEF as a centre line and a width, so a strap whose width
# and length are both an odd number of manufacturing-grid steps cannot be
# written and is silently left out (this dropped three straps: the vccd pad's
# and both vssd pads' 23.945 um stubs). Such a strap is drawn one grid step
# narrower.
from reader import click_odb, click
import odb
import re

WRAPPER_INST = "user_project"
# Must match WRAP_MARGIN_UM in scripts/extract_openframe_pads.py
WRAP_MARGIN_UM = 210.685
# How far the stripe runs past the wrapper edge. Zero: the stripe stops at the
# user-area boundary. The wrapper's edge power PORT extends 2um outside the
# boundary (and 0.3um in), so the stripe still overlaps it by 2um outside, and
# no padframe metal lands inside the user area. (It used to run 1um in, 0.7um
# past the port, and hit wide-metal spacing, MRW_met3.SP.2, against user met3.)
WRAP_OVERLAP_UM = 0.0
# Core-facing clamp pins that carry met3 stubs into the die.
CORE_FACE_PINS = {
    "VCCD", "VSSD", "VDDIO", "VSSIO", "VDDA", "VSSA", "VCCD1", "VSSD1",
}
GRID = 5        # manufacturing grid, database units
CLAMP3_PINS = ("VCCD1", "VSSD1")
CLAMP_RE = re.compile(
    r"^clamp_(vddio|vssio|vdda|vssa|vccd|vssd)(\d*)_(\d+)$"
)
# Which core-facing pin(s) feed each clamp's package rail.
PINS_FOR_BASE = {
    "vccd": {"VCCD", "VCCD1"},
    "vssd": {"VSSD", "VSSD1"},
    "vddio": {"VDDIO"},
    "vssio": {"VSSIO"},
    "vdda": {"VDDA"},
    "vssa": {"VSSA"},
}


def _met3_rects(iterm):
    """Instance-transformed met3 geometry rectangles for an ITerm."""
    inst = iterm.getInst()
    mterm = iterm.getMTerm()
    if inst is None or mterm is None:
        return []
    xform = inst.getTransform()
    out = []
    for mpin in mterm.getMPins():
        for box in mpin.getGeometry():
            layer = box.getTechLayer()
            if layer is None or layer.getName() != "met3":
                continue
            p1 = odb.Point(box.xMin(), box.yMin())
            p2 = odb.Point(box.xMax(), box.yMax())
            xform.apply(p1)
            xform.apply(p2)
            x0, x1 = sorted((p1.x(), p2.x()))
            y0, y1 = sorted((p1.y(), p2.y()))
            out.append(odb.Rect(x0, y0, x1, y1))
    return out


def _side_for_rect(r, dxl, dyl, dxh, dyh):
    """Nearest die edge for a rectangle (pad sits on that edge)."""
    cx = (r.xMin() + r.xMax()) // 2
    cy = (r.yMin() + r.yMax()) // 2
    d = {"S": cy - dyl, "N": dyh - cy, "W": cx - dxl, "E": dxh - cx}
    return min(d, key=d.get)


def _pkg_net_for_clamp(inst_name):
    """clamp_vdda1_0 -> ('vdda1', 'vdda') ; clamp_vccd_0 -> ('vccd', 'vccd')."""
    m = CLAMP_RE.match(inst_name)
    if not m:
        return None, None
    base = m.group(1)
    return base + m.group(2), base


@click.command()
@click_odb
def bridge_power_pads(reader):
    block = reader.block
    tech = block.getDataBase().getTech()
    met3 = tech.findLayer("met3")
    dbu = block.getDbUnitsPerMicron()
    wrap_edge = int(round(WRAP_MARGIN_UM * dbu))
    wrap_overlap = int(round(WRAP_OVERLAP_UM * dbu))
    die = block.getDieArea()
    dxl, dyl, dxh, dyh = die.xMin(), die.yMin(), die.xMax(), die.yMax()

    # Collect (pkg_net_name, met3_rect) from every clamp's core-facing stubs.
    work = []  # (net_name, rect)
    skipped = []
    for inst in block.getInsts():
        iname = inst.getName()
        pkg, base = _pkg_net_for_clamp(iname)
        if pkg is None:
            continue
        master = inst.getMaster().getName()
        if "clamped" not in master:
            continue
        clamped3 = master.endswith("clamped3_pad")
        accept = set(CLAMP3_PINS) if clamped3 else PINS_FOR_BASE.get(base, set())
        found = 0
        for it in inst.getITerms():
            pin_name = it.getMTerm().getName()
            if pin_name not in accept:
                continue
            # clamped3: the pin's own net (the middle stub is the other rail);
            # otherwise the clamp's package net.
            net_name = pkg
            if clamped3:
                if it.getNet() is None:
                    skipped.append((iname, f"{pin_name} has no net"))
                    continue
                net_name = it.getNet().getName()
            for r in _met3_rects(it):
                work.append((net_name, r))
                found += 1
        if not found:
            skipped.append((iname, f"no met3 stubs on {sorted(accept)}"))

    # One swire per net; create nets if needed.
    swires = {}
    bridged = 0
    narrowed = 0
    for net_name, r in work:
        net = block.findNet(net_name)
        if net is None:
            skipped.append((net_name, "net missing"))
            continue
        if net_name not in swires:
            net.setSpecial()
            swires[net_name] = odb.dbSWire.create(net, "ROUTED")
        swire = swires[net_name]
        side = _side_for_rect(r, dxl, dyl, dxh, dyh)
        if side == "W":
            x0, x1 = r.xMin(), wrap_edge + wrap_overlap
            y0, y1 = r.yMin(), r.yMax()
        elif side == "E":
            x0, x1 = dxh - wrap_edge - wrap_overlap, r.xMax()
            y0, y1 = r.yMin(), r.yMax()
        elif side == "S":
            x0, x1 = r.xMin(), r.xMax()
            y0, y1 = r.yMin(), wrap_edge + wrap_overlap
        else:  # N
            x0, x1 = r.xMin(), r.xMax()
            y0, y1 = dyh - wrap_edge - wrap_overlap, r.yMax()
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        if (x1 - x0) % (2 * GRID) and (y1 - y0) % (2 * GRID):
            # both odd: narrow the strap (its along-edge dimension) by one step
            if side in "WE":
                y1 -= GRID
            else:
                x1 -= GRID
            narrowed += 1
        odb.dbSBox.create(swire, met3, x0, y0, x1, y1, "STRIPE")
        bridged += 1

    if skipped:
        raise SystemExit(f"[bridge_power_pads] ERROR: no strap for {skipped[:8]}")
    print(
        f"[bridge_power_pads] drew {bridged} met3 clamp->wrapper straps "
        f"across {len(swires)} nets ({narrowed} narrowed by one grid step so "
        f"DEF can carry them)"
    )


if __name__ == "__main__":
    bridge_power_pads()
