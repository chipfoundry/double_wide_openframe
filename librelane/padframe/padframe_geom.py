#!/usr/bin/env python3
# Geometry helpers shared by the hand-drawn padframe steps (xres_loops.py,
# clamp_links.py): rectangles are (x0, y0, x1, y1) tuples in database units.
import odb


def xform_rect(xf, box):
    p1 = odb.Point(box.xMin(), box.yMin())
    p2 = odb.Point(box.xMax(), box.yMax())
    xf.apply(p1)
    xf.apply(p2)
    return (min(p1.x(), p2.x()), min(p1.y(), p2.y()),
            max(p1.x(), p2.x()), max(p1.y(), p2.y()))


def def_rect(r, grid=5):
    """A rectangle a DEF special wire can carry.

    DEF writes a special-net box as a centre line plus a width, so one of the
    two dimensions must be an even number of database units for the centre to
    exist; a box with both dimensions odd is silently left out of the DEF (and
    of the GDS streamed from it). Coordinates here sit on the manufacturing
    grid (`grid` units), so "odd" means an odd number of grid steps. If both
    dimensions are odd, the high x edge comes in by one grid step.
    """
    x0, y0, x1, y1 = r
    if (x1 - x0) % (2 * grid) and (y1 - y0) % (2 * grid):
        x1 -= grid
    return (x0, y0, x1, y1)


def bloat(r, d):
    return (r[0] - d, r[1] - d, r[2] + d, r[3] + d)


def overlaps(a, b):
    # strict overlap (touching edges do not count)
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def touches(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def cut_array(lo, hi, cut, pitch, margin):
    """Centres of a row of cuts between lo and hi, centred in the span."""
    span = hi - lo - 2 * margin
    if span < cut:
        return []
    n = (span - cut) // pitch + 1
    start = lo + (hi - lo - ((n - 1) * pitch + cut)) // 2 + cut // 2
    return [start + i * pitch for i in range(n)]


def pin_rects(iterm):
    """{layer: [rect, ...]} of an instance pin, in chip coordinates."""
    xf = iterm.getInst().getTransform()
    out = {}
    for mpin in iterm.getMTerm().getMPins():
        for box in mpin.getGeometry():
            layer = box.getTechLayer()
            if layer is not None:
                out.setdefault(layer.getName(), []).append(xform_rect(xf, box))
    return out


def fixed_metal(block, layers, own_nets):
    """Fixed shapes per layer as (rect, net name or None, description).

    Covers instance pins, instance obstructions and the special wiring of every
    net not in own_nets. An obstruction that touches pins of exactly one net of
    its own instance is that pin's metal (LEF abstracts split one polygon into a
    pin and an obstruction), so it is reported on that net.
    """
    shapes = {name: [] for name in layers}
    for inst in block.getInsts():
        xf = inst.getTransform()
        pins = {name: [] for name in layers}
        for it in inst.getITerms():
            net = it.getNet()
            name = net.getName() if net is not None else None
            mterm = it.getMTerm()
            for mpin in mterm.getMPins():
                for box in mpin.getGeometry():
                    layer = box.getTechLayer()
                    if layer is not None and layer.getName() in shapes:
                        r = xform_rect(xf, box)
                        pins[layer.getName()].append((r, name))
                        shapes[layer.getName()].append((
                            r, name, f"{inst.getName()}/{mterm.getName()}"))
        for box in inst.getMaster().getObstructions():
            layer = box.getTechLayer()
            if layer is None or layer.getName() not in shapes:
                continue
            r = xform_rect(xf, box)
            nets = {n for pr, n in pins[layer.getName()] if touches(r, pr)}
            shapes[layer.getName()].append((
                r, nets.pop() if len(nets) == 1 else None,
                f"{inst.getName()}:OBS"))
    for net in block.getNets():
        if net.getName() in own_nets:
            continue
        for sw in net.getSWires():
            for box in sw.getWires():
                if box.isVia():
                    continue
                layer = box.getTechLayer()
                if layer is not None and layer.getName() in shapes:
                    shapes[layer.getName()].append((
                        (box.xMin(), box.yMin(), box.xMax(), box.yMax()),
                        net.getName(), f"{net.getName()}:special"))
    return shapes
