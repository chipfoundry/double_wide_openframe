#!/usr/bin/env python3
# Add openframe-style met3 edge power/ground PORTs from pin_template.def onto
# the existing PDN ring BTerms -- without destroying the ring BPins.
#
# LibreLane's FP_TEMPLATE_COPY_POWER_PINS replaces all power BPins with the
# template ones (defutil destroys existing BPins first), which would drop the
# met4/met5 ring ports. We only *append* the clamp-aligned edge ports so both
# coexist: rings for in-macro distribution, edge ports for padframe straps.
import re
import os

from reader import click_odb, click
import odb

POWER_NETS = {
    "vccd", "vccd1", "vccd2", "vddio", "vdda", "vdda1", "vdda2",
    "vssd", "vssd1", "vssd2", "vssio", "vssa", "vssa1", "vssa2",
}
M3M4_VIA = "M3M4_PR"
STRAP_WIDTH_DBU = 1600
MIN_PDN_STRIPE_LENGTH_DBU = 4000


def _parse_power_ports(def_path):
    """Return {pin_name: [(layer, x1, y1, x2, y2), ...]} from a pins-only DEF."""
    text = open(def_path).read()
    ports = {n: [] for n in POWER_NETS}
    # Multi-PORT power pins as emitted by gen_pin_template_def().
    for m in re.finditer(
        r"- (\w+) \+ NET \1 \+ SPECIAL \+ DIRECTION INOUT \+ USE (?:POWER|GROUND)\n"
        r"(.*?)(?=\n- |\nEND PINS)",
        text,
        re.S,
    ):
        name, body = m.group(1), m.group(2)
        if name not in POWER_NETS:
            continue
        for box in re.finditer(
            r"LAYER (\w+) \( ([-\d]+) ([-\d]+) \) \( ([-\d]+) ([-\d]+) \)",
            body,
        ):
            layer, x1, y1, x2, y2 = box.group(1), *map(int, box.groups()[1:])
            ports[name].append((layer, x1, y1, x2, y2))
    return ports


def _met4_stripes(net):
    """Return the long vertical met4 shapes in an existing PDN mesh."""
    stripes = []
    for swire in net.getSWires():
        for box in swire.getWires():
            if box.isVia():
                continue
            layer = box.getTechLayer()
            if layer is None or layer.getName() != "met4":
                continue
            if (
                box.yMax() - box.yMin() > box.xMax() - box.xMin()
                and box.yMax() - box.yMin() >= MIN_PDN_STRIPE_LENGTH_DBU
            ):
                stripes.append(box)
    return stripes


def _add_rect(swire, layer, x1, y1, x2, y2):
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    if x1 != x2 and y1 != y2:
        odb.dbSBox.create(swire, layer, x1, y1, x2, y2, "STRIPE")


def _stitch_ports_to_pdn(block, tech, ports):
    """Route edge ports on met3 to each net's nearest internal met4 PDN stripe."""
    met3 = tech.findLayer("met3")
    via = tech.findVia(M3M4_VIA)
    if met3 is None or via is None:
        raise RuntimeError("met3 or M3M4_PR is unavailable")

    die = block.getDieArea()
    half = STRAP_WIDTH_DBU // 2
    stitched = 0
    skipped = []
    for name, boxes in ports.items():
        net = block.findNet(name)
        if net is None:
            continue
        stripes = _met4_stripes(net)
        if not stripes:
            # An unused top-level supply has no in-macro PDN to stitch.
            continue
        net.setSpecial()
        swire = odb.dbSWire.create(net, "ROUTED")
        for _layer, x1, y1, x2, y2 in boxes:
            px = (x1 + x2) // 2
            py = (y1 + y2) // 2
            if x1 < die.xMin():  # west
                ax, ay = die.xMin(), py
            elif x2 > die.xMax():  # east
                ax, ay = die.xMax(), py
            elif y1 < die.yMin():  # south
                ax, ay = px, die.yMin()
            elif y2 > die.yMax():  # north
                ax, ay = px, die.yMax()
            else:
                skipped.append((name, "port does not touch an edge"))
                continue

            spanning = [s for s in stripes if s.yMin() <= ay <= s.yMax()]
            candidates = spanning or stripes
            stripe = min(
                candidates,
                key=lambda s: (
                    abs((s.xMin() + s.xMax()) // 2 - ax)
                    + max(s.yMin() - ay, 0, ay - s.yMax())
                ),
            )
            vx = (stripe.xMin() + stripe.xMax()) // 2
            vy = min(max(ay, stripe.yMin() + half), stripe.yMax() - half)

            if ax in (die.xMin(), die.xMax()):
                _add_rect(swire, met3, ax, ay - half, vx, ay + half)
                _add_rect(swire, met3, vx - half, ay, vx + half, vy)
            else:
                _add_rect(swire, met3, ax - half, ay, ax + half, vy)
                _add_rect(swire, met3, ax, vy - half, vx, vy + half)
            odb.dbSBox.create(swire, via, vx, vy, "STRIPE")
            stitched += 1

    if skipped:
        print(f"[add_power_edge_ports] WARNING stitch skips {skipped[:8]}")
    print(f"[add_power_edge_ports] stitched {stitched} edge ports into the PDN")


@click.command()
@click.option(
    "-t",
    "--def-template",
    required=True,
    help="Pin template DEF (same as FP_DEF_TEMPLATE)",
)
@click_odb
def add_power_edge_ports(reader, def_template):
    block = reader.block
    tech = block.getDataBase().getTech()
    ports = _parse_power_ports(def_template)
    added = 0
    skipped = []
    for name, boxes in ports.items():
        if not boxes:
            continue
        bterm = block.findBTerm(name)
        if bterm is None:
            skipped.append((name, "no BTerm"))
            continue
        bpins = bterm.getBPins()
        if bpins:
            bpin = bpins[0]
        else:
            bpin = odb.dbBPin.create(bterm)
            bpin.setPlacementStatus("FIRM")
        for layer_name, x1, y1, x2, y2 in boxes:
            layer = tech.findLayer(layer_name)
            if layer is None:
                skipped.append((name, f"missing layer {layer_name}"))
                continue
            odb.dbBox.create(bpin, layer, x1, y1, x2, y2)
            added += 1
            print(
                f"[add_power_edge_ports] {name} +{layer_name} "
                f"({x1},{y1})-({x2},{y2})"
            )
    if skipped:
        print(f"[add_power_edge_ports] WARNING skipped {skipped[:8]}")
    print(f"[add_power_edge_ports] added {added} edge power/ground ports")
    _stitch_ports_to_pdn(block, tech, ports)


if __name__ == "__main__":
    add_power_edge_ports()
