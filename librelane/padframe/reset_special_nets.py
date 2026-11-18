#!/usr/bin/env python3
# Mark the POR outputs and the reset-pad-local loops SPECIAL so TritonRoute
# leaves them alone.
#
# por_l/porb_l/porb_h are thin met3 pins on simple_por ~113um from the wrapper
# west edge whose centers never land on a met3 routing track, so DRT can build
# no access point for them (DRT-0419) and then asserts/crashes in initRPin. They
# reach the wrapper pins through the simple_por GDS collar instead; porb_h also
# reaches the pad enables through Padframe.PorbRing. resetb_h / resetb_l get
# access points and are routed normally by TritonRoute, so they are NOT listed.
#
# The three xres* nets below are drawn by Padframe.XresLoops, the way the
# openframe hand-draws them.
from reader import click_odb, click

SPECIAL_NETS = [
    # simple_por level-shifter outputs: thin met3 pins ~113um from the wrapper
    # that never get a routing access point; they reach the wrapper pins through
    # the simple_por GDS collar.
    "por_l",
    "porb_l",
    # xres-pad-internal tie / loopback nets (master_resetb_pad ESD/tie pins and
    # the xres constant_block .one), clustered in the tight south ring with no
    # DRT access. Drawn by Padframe.XresLoops.
    "xresloop",
    "xres_vss_loop",
    "xres_loopback_one",
    # NOTE: resetb_l (rstb_level.X -> wrapper.resetb_l) and resetb_h
    # (pad.XRES_H_N -> rstb_level.A -> wrapper.resetb_h) are NOT listed here --
    # both are routed by TritonRoute (their pins get DRT access points), per
    # request.
    # simple_por high-side output. Reaches the wrapper porb_h pin through the
    # simple_por GDS collar, and every pad ENABLE_H / ENABLE_VDDA_H through the
    # hand-drawn met1 loop of Padframe.PorbRing (openframe-style). Must stay
    # SPECIAL so TritonRoute neither routes it nor rips that wiring up.
    "porb_h",
]
# NOTE: none of the POR outputs are routed by DRT; por_l/porb_l/porb_h reach
# the wrapper through the simple_por collar, porb_h reaches the pads via
# Padframe.PorbRing.


@click.command()
@click_odb
def reset_special_nets(reader):
    block = reader.block
    marked = []
    missing = []
    for name in SPECIAL_NETS:
        net = block.findNet(name)
        if net is None:
            missing.append(name)
            continue
        net.setSpecial()
        marked.append(name)
    if missing:
        print(
            "[reset_special_nets] WARNING: not found:",
            ", ".join(missing),
        )
    print(f"[reset_special_nets] marked SPECIAL: {len(marked)} nets")


if __name__ == "__main__":
    reset_special_nets()
