#!/usr/bin/env python3
# Padframe.WrapperPinLanding: padframe metal over every wrapper pin footprint.
#
# A wrapper pin crosses the user-area boundary: 2.0 um outside, 0.28 um (met2)
# or 0.30 um (met3) inside. In the caravel openframe the padframe's own metal
# covers that whole footprint for every signal pin and power port, so the
# connection is complete in the padframe by itself and a user wrapper dropped in
# simply overlaps it. The router only has to touch a pin to connect to it, and
# does: it stops at the pin's outer tip, which left the landing metal in the
# wrapper cell alone.
#
# After detailed routing this step draws, for every pin shape of the wrapper
# instance, that exact rectangle on the pin's net. The shape is the pin's own,
# so it adds no metal the wrapper does not already have, and the only padframe
# metal inside the user area stays within the wrapper's pin footprints.
#
# On a routed signal net the rectangle is added to the net's wiring as a patch
# (DEF `RECT`, what the router itself uses for minimum-area fixes), so the net
# stays an ordinary routed net. Power and the other SPECIAL nets get a special
# wire, which DEF only writes for SPECIAL nets.
import os
import sys

from reader import click_odb, click
import odb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from padframe_geom import def_rect, xform_rect  # noqa: E402

WRAPPER_INST = "user_project"
LAYERS = ("met2", "met3")


@click.command()
@click_odb
def wrapper_pin_landing(reader):
    block = reader.block
    tech = block.getDataBase().getTech()
    dbu = block.getDbUnitsPerMicron()
    wrapper = block.findInst(WRAPPER_INST)
    if wrapper is None:
        raise SystemExit(f"[wrapper_pin_landing] ERROR: instance {WRAPPER_INST} not found")
    xf = wrapper.getTransform()

    swires = {}
    patched = set()
    drawn = {ly: 0 for ly in LAYERS}
    unconnected = []
    for it in wrapper.getITerms():
        net = it.getNet()
        pin = it.getMTerm().getName()
        rects = []
        for mpin in it.getMTerm().getMPins():
            for box in mpin.getGeometry():
                layer = box.getTechLayer()
                if layer is not None:
                    rects.append((layer.getName(), xform_rect(xf, box)))
        if not rects:
            continue
        if net is None:
            unconnected.append(pin)
            continue
        for ly, r in rects:
            if ly not in LAYERS:
                raise SystemExit(
                    f"[wrapper_pin_landing] ERROR: {pin} has a pin shape on {ly}")
            if def_rect(r) != r:
                raise SystemExit(
                    f"[wrapper_pin_landing] ERROR: {pin} {[v / dbu for v in r]} "
                    "cannot be written to DEF exactly")
            name = net.getName()
            layer = tech.findLayer(ly)
            if net.isSpecial():
                if name not in swires:
                    swires[name] = odb.dbSWire.create(net, "ROUTED")
                odb.dbSBox.create(swires[name], layer, *r, "STRIPE")
            else:
                cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
                enc = odb.dbWireEncoder()
                wire = net.getWire()
                if wire is None:
                    enc.begin(odb.dbWire.create(net))
                else:
                    enc.append(wire)
                enc.newPath(layer, "ROUTED")
                enc.addPoint(cx, cy)
                enc.addRect(r[0] - cx, r[1] - cy, r[2] - cx, r[3] - cy)
                enc.end()
                patched.add(name)
            drawn[ly] += 1
    if unconnected:
        raise SystemExit(
            f"[wrapper_pin_landing] ERROR: wrapper pins with no net: {unconnected[:8]}")
    print(f"[wrapper_pin_landing] {sum(drawn.values())} pin footprints covered "
          f"({', '.join(f'{n} {ly}' for ly, n in drawn.items())}): "
          f"{len(patched)} routed nets patched, {len(swires)} special nets")


if __name__ == "__main__":
    wrapper_pin_landing()
