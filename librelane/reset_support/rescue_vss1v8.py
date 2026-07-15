#!/usr/bin/env python3
# Reconnect simple_por/vss1v8 and draw its met1 abutment + via stack into the
# vssd grid. Runs on the post-GeneratePDN odb (Reset.RescueVss1v8 step), so the
# vssd mesh/ring already exist and we can pick a real target stripe to land on.
#
# Why this is needed: vss1v8 is a ~0.36 x 0.7 um met1 nub at simple_por's top-
# left corner, and the cell's own met2/met3 OBS blanket that nub. A via straight
# up is impossible, so pdngen aborts (PDN-0006). pdn_cfg.tcl detaches the iterm
# so pdngen skips it; here we reconnect it and route it the only way possible --
# laterally on met1 into the clear column left of the cell, then up a via stack
# onto the nearest vssd met4 stripe (interior mesh, else the left core-ring strap).
import sys

import click
import odb
from reader import click_odb

INST_NAME = "por"
PIN_NAME = "vss1v8"
GND_NET = "vssd"
VIA_STACK = ["M1M2_PR", "M2M3_PR", "M3M4_PR"]  # met1->met2->met3->met4
MIN_STRIPE_LEN_DBU = 4000  # 4um: ignore small via/enclosure patches when hunting stripes

# user_id_programming met5 power pins. Each is bridged to the nearest same-net
# met5 mesh stripe with a short vertical met4 jog placed in the cell's left
# met4-clear strip (local x < ~8.78 um). (inst, pin, net, local x of the jog).
UID_INST = "user_id_value"
UID_TAPS = [
    ("VPWR", "vccd", 6.4),
    ("VGND", "vssd", 8.0),
]
M4M5_VIA = "M4M5_PR"
M4_JOG_W = 600  # 0.6um met4 jog width (DBU)


def _pin_box(iterm, layer_name):
    """Global (DBU) rect of the pin on layer_name, honoring placement/orientation."""
    inst = iterm.getInst()
    px, py = inst.getOrigin()
    transform = odb.dbTransform(inst.getOrient(), odb.Point(px, py))
    for mpin in iterm.getMTerm().getMPins():
        for box in mpin.getGeometry():
            layer = box.getTechLayer()
            if layer is None or layer.getName() != layer_name:
                continue
            ll = odb.Point(box.xMin(), box.yMin())
            ur = odb.Point(box.xMax(), box.yMax())
            transform.apply(ll)
            transform.apply(ur)
            return ll.getX(), ll.getY(), ur.getX(), ur.getY()
    return None


def _nearest_met5_stripe(net, xc, yc):
    """Nearest horizontal met5 mesh stripe of `net` (by Y) that spans xc."""
    best = None
    best_dy = None
    for swire in net.getSWires():
        for sb in swire.getWires():
            if sb.isVia():
                continue
            layer = sb.getTechLayer()
            if layer is None or layer.getName() != "met5":
                continue
            w = sb.xMax() - sb.xMin()
            h = sb.yMax() - sb.yMin()
            if w <= h or w < MIN_STRIPE_LEN_DBU:  # horizontal stripes only
                continue
            if not (sb.xMin() <= xc <= sb.xMax()):  # must span the jog X
                continue
            sy = (sb.yMin() + sb.yMax()) // 2
            dy = abs(sy - yc)
            if best is None or dy < best_dy:
                best = sb
                best_dy = dy
    return best


def _nearest_left_met4_stripe(net, nub_x0, yc):
    """The vssd met4 vertical stripe/ring strap closest to (but left of) the nub."""
    best = None
    for swire in net.getSWires():
        for box in swire.getWires():
            if box.isVia():
                continue
            layer = box.getTechLayer()
            if layer is None or layer.getName() != "met4":
                continue
            w = box.xMax() - box.xMin()
            h = box.yMax() - box.yMin()
            if h <= w or h < MIN_STRIPE_LEN_DBU:  # vertical stripes only
                continue
            if box.xMax() >= nub_x0:  # must sit left of the nub (clear column)
                continue
            if not (box.yMin() <= yc <= box.yMax()):  # must span the strap Y
                continue
            if best is None or box.xMax() > best.xMax():
                best = box
    return best


@click.command()
@click_odb
def rescue(reader):
    block = reader.block
    tech = reader.tech

    inst = block.findInst(INST_NAME)
    if inst is None:
        print(f"[rescue] instance '{INST_NAME}' not found", file=sys.stderr)
        sys.exit(1)
    net = block.findNet(GND_NET)
    if net is None:
        print(f"[rescue] net '{GND_NET}' not found", file=sys.stderr)
        sys.exit(1)
    iterm = inst.findITerm(PIN_NAME)
    if iterm is None:
        print(f"[rescue] {INST_NAME}/{PIN_NAME} iterm not found", file=sys.stderr)
        sys.exit(1)

    # 1) Reconnect the iterm pdn_cfg.tcl detached so pdngen would skip it.
    iterm.connect(net)

    pin = _pin_box(iterm, "met1")
    if pin is None:
        print(f"[rescue] no met1 geometry on {INST_NAME}/{PIN_NAME}", file=sys.stderr)
        sys.exit(1)
    pin_x0, pin_y0, pin_x1, pin_y1 = pin
    yc = (pin_y0 + pin_y1) // 2

    target = _nearest_left_met4_stripe(net, pin_x0, yc)
    if target is None:
        print("[rescue] no vssd met4 stripe found left of the nub", file=sys.stderr)
        sys.exit(1)
    target_x = (target.xMin() + target.xMax()) // 2

    met1 = reader.layers["met1"]
    swire = odb.dbSWire_create(net, "ROUTED")

    # 2) Lateral met1 strap: from over the target stripe (for via enclosure) to
    #    the pin, at the pin's Y band. Left of simple_por the core is empty, so
    #    the only metal this crosses is other-net stripes on higher layers.
    odb.dbSBox_create(swire, met1, target_x, pin_y0, pin_x1, pin_y1, "STRIPE")

    # 3) met1 -> met4 via stack on the target stripe.
    for via_name in VIA_STACK:
        via = tech.findVia(via_name)
        if via is None:
            print(f"[rescue] tech via '{via_name}' not found", file=sys.stderr)
            sys.exit(1)
        odb.dbSBox_create(swire, via, target_x, yc, "STRIPE")

    print(
        f"[rescue] {INST_NAME}/{PIN_NAME} -> {GND_NET}: met1 strap "
        f"x[{target_x}..{pin_x1}] y[{pin_y0}..{pin_y1}] + via stack at x={target_x}"
    )

    # 4) user_id_programming met5 power pins. pdngen leaves them unconnected
    #    (VPWR/VGND detached in pdn_cfg.tcl) because the met4 under the cell is
    #    OBS-blocked and the pins run parallel to the met5 mesh (PDN-0232). For
    #    each pin: reconnect it, then bridge it to the nearest same-net met5 mesh
    #    stripe with a short vertical met4 jog dropped in the cell's left met4-clear
    #    strip -- M4M5 via at the pin (top) and at the mesh stripe (bottom).
    m4m5 = tech.findVia(M4M5_VIA)
    if m4m5 is None:
        print(f"[rescue] tech via '{M4M5_VIA}' not found", file=sys.stderr)
        sys.exit(1)
    met4 = reader.layers["met4"]
    uinst = block.findInst(UID_INST)
    if uinst is None:
        print(f"[rescue] instance '{UID_INST}' not found", file=sys.stderr)
        sys.exit(1)
    uid_x0 = uinst.getBBox().xMin()
    for pin_name, net_name, jog_dx in UID_TAPS:
        unet = block.findNet(net_name)
        uit = uinst.findITerm(pin_name)
        if unet is None or uit is None:
            print(f"[rescue] {UID_INST}/{pin_name} ({net_name}) missing", file=sys.stderr)
            sys.exit(1)
        uit.connect(unet)
        pbox = _pin_box(uit, "met5")
        if pbox is None:
            print(f"[rescue] no met5 geom on {UID_INST}/{pin_name}", file=sys.stderr)
            sys.exit(1)
        pin_yc = (pbox[1] + pbox[3]) // 2
        jog_x = uid_x0 + int(jog_dx * 1000)
        stripe = _nearest_met5_stripe(unet, jog_x, pin_yc)
        if stripe is None:
            print(f"[rescue] no {net_name} met5 mesh stripe over x={jog_x}", file=sys.stderr)
            sys.exit(1)
        stripe_yc = (stripe.yMin() + stripe.yMax()) // 2
        jy0 = min(pin_yc, stripe_yc)
        jy1 = max(pin_yc, stripe_yc)
        usw = odb.dbSWire_create(unet, "ROUTED")
        # vertical met4 jog in the clear strip, spanning pin Y .. mesh-stripe Y.
        odb.dbSBox_create(
            usw, met4, jog_x - M4_JOG_W // 2, jy0, jog_x + M4_JOG_W // 2, jy1, "STRIPE"
        )
        # via to the met5 pin (top) and to the met5 mesh stripe (bottom).
        odb.dbSBox_create(usw, m4m5, jog_x, pin_yc, "STRIPE")
        odb.dbSBox_create(usw, m4m5, jog_x, stripe_yc, "STRIPE")
        print(
            f"[rescue] {UID_INST}/{pin_name} -> {net_name}: met4 jog x={jog_x} "
            f"y[{jy0}..{jy1}] + vias at pin y={pin_yc}, mesh y={stripe_yc}"
        )


if __name__ == "__main__":
    rescue()
