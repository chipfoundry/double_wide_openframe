#!/usr/bin/env python3
# Bridge each gpio_dm0[i] detailed route to its own DM[0] pad pin.
#
# DM[0] on the sky130 gpiov2 pad is a short met2 tip stub. After detailed
# routing the gpio_dm0[i] wire reaches the pin but stops ~0.07-0.13um short of
# the pin metal (they connect through the via/lower layers, not by met2 overlap),
# leaving a *same-net* met2-met2 gap that KLayout signs off as m2.2. Only
# gpio_dm0 metal is present there (verified: the stock pad cell is clean near
# DM[0] and no other net is within 2um), so we merge the two shapes with a small
# same-net met2 patch: widen the pin over its access notch and extend it toward
# the core so it overlaps the route. Electrically a no-op (same net); it just
# removes the sub-spacing gap.
from reader import click_odb, click
import odb

WIDEN_UM = 0.80   # widen the patch along the edge to engulf the (offset) route wire;
                  # the pin band is walled with no other net within ~3um, so safe.
# Extend the patch core-ward to the walled DM[0] pin-band depth (== the generator's
# PIN_STRIP_DEPTH_UM). The whole band is flanked by routing obstructions and holds
# only this net's DM[0] metal, so filling it end-to-end merges pin+route+any residual
# same-net notch without risking a short into the fan-out region above the band.
BAND_DEPTH_UM = 200.5


@click.command()
@click_odb
def bridge_dm0(reader):
    block = reader.block
    tech = block.getDataBase().getTech()
    met2 = tech.findLayer("met2")
    dbu = block.getDbUnitsPerMicron()
    widen = int(WIDEN_UM * dbu)
    band = int(BAND_DEPTH_UM * dbu)
    die = block.getDieArea()
    dxl, dyl, dxh, dyh = die.xMin(), die.yMin(), die.xMax(), die.yMax()

    bridged = 0
    skipped = []
    all_nets = block.getNets()
    matched = [n for n in all_nets if "dm0" in n.getName()]
    print(f"[bridge_dm0] {len(all_nets)} nets, {len(matched)} match 'dm0'")
    for net in matched:
        name = net.getName()
        # DM[0] pin iterm = the one on a gpiov2 pad instance
        pin_iterm = None
        for it in net.getITerms():
            inst = it.getInst()
            if inst is not None and "gpiov2_pad" in inst.getMaster().getName():
                pin_iterm = it
                break
        if pin_iterm is None:
            skipped.append((name, "no gpiov2 iterm"))
            continue
        # DM[0] pin bbox in global coords (it is a met2 tip stub)
        bb = pin_iterm.getBBox()
        xl, yl, xh, yh = bb.xMin(), bb.yMin(), bb.xMax(), bb.yMax()

        # nearest die edge -> core direction; widen along the edge, extend to core
        d = {"S": yl - dyl, "N": dyh - yh, "W": xl - dxl, "E": dxh - xh}
        side = min(d, key=d.get)
        if side in ("N", "S"):
            px0, px1 = xl - widen, xh + widen           # widen along X (the edge)
            py0 = min(yl, dyh - band) if side == "N" else yl   # extend to band depth (core)
            py1 = yh if side == "N" else max(yh, dyl + band)
        else:
            py0, py1 = yl - widen, yh + widen           # widen along Y (the edge)
            px0 = min(xl, dxh - band) if side == "E" else xl   # extend to band depth (core)
            px1 = xh if side == "E" else max(xh, dxl + band)

        net.setSpecial()
        swire = odb.dbSWire.create(net, "ROUTED")
        odb.dbSBox.create(swire, met2, px0, py0, px1, py1, "STRIPE")
        bridged += 1

    if skipped:
        print(f"[bridge_dm0] WARNING skipped {len(skipped)}: {skipped[:5]}")
    print(f"[bridge_dm0] bridged DM[0] pin<->route on {bridged} gpio_dm0 nets")


if __name__ == "__main__":
    bridge_dm0()
