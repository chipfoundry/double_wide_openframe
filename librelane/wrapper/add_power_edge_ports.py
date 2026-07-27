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
        for layer_name, x1, y1, x2, y2 in boxes:
            layer = tech.findLayer(layer_name)
            if layer is None:
                skipped.append((name, f"missing layer {layer_name}"))
                continue
            bpin = odb.dbBPin.create(bterm)
            bpin.setPlacementStatus("FIRM")
            odb.dbBox.create(bpin, layer, x1, y1, x2, y2)
            added += 1
            print(
                f"[add_power_edge_ports] {name} +{layer_name} "
                f"({x1},{y1})-({x2},{y2})"
            )
    if skipped:
        print(f"[add_power_edge_ports] WARNING skipped {skipped[:8]}")
    print(f"[add_power_edge_ports] added {added} edge power/ground ports")


if __name__ == "__main__":
    add_power_edge_ports()
