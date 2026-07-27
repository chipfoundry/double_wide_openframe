#!/usr/bin/env python3
# Mark the two unroutable simple_por outputs SPECIAL so TritonRoute leaves them
# alone; they connect to the wrapper por pins by abutment at integrate time
# (same approach as caravel's hand-routed reset cluster).
#
# por_l/porb_l are thin met3 pins on simple_por ~113um from the wrapper west
# edge whose centers never land on a met3 routing track, so DRT can build no
# access point for them (DRT-0419) and then asserts/crashes in initRPin. The
# rest of the reset/POR cluster (porb_h, resetb_h, resetb_l, xres*) DOES get
# access points and is routed normally by TritonRoute, so it is NOT listed here.
from reader import click_odb, click

SPECIAL_NETS = [
    # simple_por level-shifter outputs: thin met3 pins ~113um from the wrapper
    # that never get a routing access point; connect by abutment at integrate.
    "por_l",
    "porb_l",
    # xres-pad-internal tie / loopback nets (master_resetb_pad ESD/tie pins and
    # the xres constant_block .one), clustered in the tight south ring with no
    # DRT access. Local abutment loops, not wrapper-facing, so leave them to DRT
    # -free abutment (exactly as the proven Jul-15 run did).
    "xresloop",
    "xres_vss_loop",
    "xres_loopback_one",
    # xres_buf reset outputs/inputs: connect by abutment, not DRT.
    #   resetb_l = rstb_level.X -> wrapper.resetb_l   (buf output abuts wrapper pin)
    #   resetb_h = pad.XRES_H_N -> rstb_level.A -> wrapper.resetb_h
    #     (pin A abuts; the whole net is per-net SPECIAL so DRT skips pin A too)
    "resetb_l",
    "resetb_h",
    # simple_por high-side output: abut to the wrapper porb_h pin, not routed.
    "porb_h",
]
# NOTE: all wrapper-facing reset/POR nets now connect by abutment at integrate;
# none are routed by DRT.


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
