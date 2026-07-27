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
# met3 stubs live on the abutment pin (VDDA/VSSA -> global vdda/vssa); the
# stripe still overlaps that stub metal, intentionally shorting the domain
# rail to the shared analog ring the same way the clamp does internally.
from reader import click_odb, click
import odb
import re

WRAPPER_INST = "user_project"
# Must match WRAP_MARGIN_UM in scripts/extract_openframe_pads.py
WRAP_MARGIN_UM = 210.685
# Overlap past the wrapper edge so the stripe covers the edge power PORT
# (openframe-style pin extends ~0.3um into the wrapper die).
WRAP_OVERLAP_UM = 1.0
# Core-facing clamp pins that carry met3 stubs into the die.
CORE_FACE_PINS = {
    "VCCD", "VSSD", "VDDIO", "VSSIO", "VDDA", "VSSA", "VCCD1", "VSSD1",
}
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
        accept = PINS_FOR_BASE.get(base, set())
        rects = []
        for it in inst.getITerms():
            pin_name = it.getMTerm().getName()
            if pin_name not in accept:
                continue
            rects.extend(_met3_rects(it))
        if not rects:
            skipped.append((iname, f"no met3 stubs on {sorted(accept)}"))
            continue
        for r in rects:
            work.append((pkg, r))

    # One swire per net; create nets if needed.
    swires = {}
    bridged = 0
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
        odb.dbSBox.create(swire, met3, x0, y0, x1, y1, "STRIPE")
        bridged += 1

    if skipped:
        print(f"[bridge_power_pads] WARNING skipped {len(skipped)}: {skipped[:8]}")
    print(
        f"[bridge_power_pads] drew {bridged} met3 clamp->wrapper straps "
        f"across {len(swires)} nets"
    )


if __name__ == "__main__":
    bridge_power_pads()
