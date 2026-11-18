#!/usr/bin/env python3
"""Check the wrapper's pins against the caravel openframe, and the padframe's
metal against the wrapper's pins.

    python3 scripts/check_wrapper_pins.py [--caravel-def ../caravel/def/openframe_project_wrapper.def]
                                          [--gds gds/double_wide_chip_io.gds]

1. Template. Every GPIO pad's pins in librelane/wrapper/pin_template.def must be
   the pins of the openframe pad it copies: same layer, same width, same reach
   outside and inside the boundary, same offset from the pad. Every clamp pad's
   power ports likewise. Compared as multisets of (layer, width, out, in) per
   signal and edge, plus each pad's pin offsets.
2. Layout. In the padframe GDS, with the wrapper cell removed, the padframe's
   own metal must cover the whole footprint of every wrapper pin shape, signal
   and power. A pin the padframe only touches, or a power port with no strap on
   it, fails.

3. Pads. In the padframe DEF every GPIO, clamp and reset pad cell must sit
   where the openframe has it, with the openframe's orientation (never
   mirrored): west and east as they are, north and south twice with the
   right-hand copy 3588 um on (the reset pad once). The four seam GPIO pads
   have no openframe counterpart and are only checked for orientation.

Needs the klayout Python module. Exits non-zero on any difference.
"""
import argparse
import collections
import os
import re
import sys

import klayout.db as kdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import extract_openframe_pads as gen  # noqa: E402

WRAPPER = "double_wide_openframe_project_wrapper"
GDS_LAYERS = {"met2": (69, 20), "met3": (70, 20)}


def template_shapes(path, w, h):
    """[(base, index, side, layer, lo, hi, out, inn)] in wrapper nm."""
    out = []
    name = None
    for line in open(path).read().splitlines():
        m = re.match(r"- (\S+) \+ NET", line)
        if m:
            name = m.group(1)
        b = re.search(r"\+ LAYER (\w+) \( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \)", line)
        if not (b and name):
            continue
        layer = b.group(1)
        x1, y1, x2, y2 = (int(v) for v in b.groups()[1:])
        if x1 < 0:
            side, lo, hi, o, i = "W", y1, y2, -x1, x2
        elif x2 > w:
            side, lo, hi, o, i = "E", y1, y2, x2 - w, w - x1
        elif y1 < 0:
            side, lo, hi, o, i = "S", x1, x2, -y1, y2
        else:
            side, lo, hi, o, i = "N", x1, x2, y2 - h, h - y1
        nm = re.match(r"(\w+)\[(\d+)\]$", name)
        base, index = (nm.group(1), int(nm.group(2))) if nm else (name, None)
        out.append((base, index, side, layer, lo, hi, o, i, (x1, y1, x2, y2)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--caravel-def", default=gen.DEFAULT_OPENFRAME_DEF)
    ap.add_argument("--template", default=os.path.join(ROOT, "librelane/wrapper/pin_template.def"))
    ap.add_argument("--gds", default=os.path.join(ROOT, "gds/double_wide_chip_io.gds"))
    ap.add_argument("--def", dest="def_path",
                    default=os.path.join(ROOT, "def/double_wide_chip_io.def"))
    ap.add_argument("--caravel-mag", default=os.path.join(
        os.path.dirname(gen.DEFAULT_OPENFRAME_DEF), "..", "mag", "chip_io_openframe.mag"))
    args = ap.parse_args()
    errors = []

    # ---- 1. template against the openframe -------------------------------
    gen.OPENFRAME_DEF["path"] = args.caravel_def
    of = gen.openframe_pins()
    w, h = round(gen.WRAP_W_UM * 1000), round(gen.WRAP_H_UM * 1000)
    dw = template_shapes(args.template, w, h)
    skip = {"mask_rev", "porb_h", "por_l", "porb_l", "resetb_h", "resetb_l"}

    def kinds(shapes):
        c = collections.defaultdict(set)
        for s in shapes:
            c[(s[0], s[2])].add((s[3], s[5] - s[4], s[6], s[7]))
        return c
    of_kinds = kinds([(p["base"], p["index"], p["side"], p["layer"], p["lo"], p["hi"],
                       p["out"], p["inn"]) for p in of])
    dw_kinds = kinds(dw)
    for key in sorted(set(of_kinds) | set(dw_kinds)):
        if key[0] in skip:
            if of_kinds.get(key) != dw_kinds.get(key):
                errors.append(f"{key[0]} on {key[1]}: openframe {sorted(of_kinds.get(key, []))}, "
                              f"here {sorted(dw_kinds.get(key, []))}")
            continue
        extra = dw_kinds.get(key, set()) - of_kinds.get(key, set())
        if extra:
            errors.append(f"{key[0]} on {key[1]}: shape(s) {sorted(extra)} not in the openframe")
    # offsets inside a pad: every GPIO's pins, relative to its gpio_in pin
    def rel(shapes):
        by = collections.defaultdict(dict)
        for base, index, side, layer, lo, hi, *_ in shapes:
            if index is not None and base not in skip:
                by[index][base] = (side, lo)
        out = collections.Counter()
        for index, pins in by.items():
            side, ref = pins["gpio_in"]
            out[(side, tuple(sorted((b, lo - ref) for b, (_, lo) in pins.items())))] += 1
        return out
    of_rel = rel([(p["base"], p["index"], p["side"], p["layer"], p["lo"], p["hi"]) for p in of])
    dw_rel = rel(dw)
    unknown = [k for k in dw_rel if k not in of_rel]
    if unknown:
        errors.append(f"{sum(dw_rel[k] for k in unknown)} GPIO pad(s) have a pin layout "
                      "that no openframe pad has")
    n_gpio = sum(dw_rel.values())
    print(f"template: {len(dw)} pin shapes, {n_gpio} GPIO pads in "
          f"{len(dw_rel)} pin layouts, all found in the openframe: {not unknown}")

    # ---- 2. padframe metal on every pin footprint -------------------------
    layout = kdb.Layout()
    layout.read(args.gds)
    top = layout.top_cell()
    inst = [i for i in top.each_inst() if i.cell.name == WRAPPER]
    if len(inst) != 1:
        sys.exit(f"{args.gds}: expected one {WRAPPER} instance")
    ox, oy = inst[0].trans.disp.x, inst[0].trans.disp.y
    inst[0].delete()
    dbu = layout.dbu
    scale = round(0.001 / dbu)
    bare = collections.Counter()
    for base, index, side, layer, lo, hi, o, i, (x1, y1, x2, y2) in dw:
        box = kdb.Box(x1 * scale + ox, y1 * scale + oy, x2 * scale + ox, y2 * scale + oy)
        li = layout.find_layer(*GDS_LAYERS[layer])
        metal = (kdb.Region(top.begin_shapes_rec_overlapping(li, box)) & kdb.Region(box)).merged()
        if metal.area() != box.area():
            name = base if index is None else f"{base}[{index}]"
            bare[name] += 1
            if len(bare) <= 8:
                errors.append(f"{name} {layer} footprint {kdb.DBox(box) * dbu}: padframe "
                              f"metal covers {100 * metal.area() / box.area():.0f}%")
    print(f"layout: padframe metal covers the whole footprint of "
          f"{len(dw) - sum(bare.values())} of {len(dw)} wrapper pin shapes")
    if len(bare) > 8:
        errors.append(f"... and {len(bare) - 8} more pins")

    # ---- 3. pad cells where the openframe has them -------------------------
    uses = gen.parse_mag(args.caravel_mag)
    gen.classify(uses)
    want = collections.Counter()
    for u in uses:
        if getattr(u, "lo", None) is None:
            continue
        orient = gen.SIDE_ORIENT[u.side]
        # north and south are the openframe's twice; the reset pad only once
        twice = u.side in "NS" and u.master != gen.XRES_MASTER
        copies = (0.0, gen.HALF_UM) if twice else (0.0,)
        for d in copies:
            want[(u.master, u.side, round(u.lo + d, 3), orient)] += 1
    text = open(args.def_path).read()
    comp = text[text.index("\nCOMPONENTS"):text.index("END COMPONENTS")]
    die_w, die_h = gen.DW_W_UM, gen.DW_H_UM
    have = collections.Counter()
    for m in re.finditer(r"- (\S+) (sky130_ef_io__\w+_pad|sky130_fd_io__top_xres4v2)"
                         r"[^;]*?\+ (?:FIXED|PLACED) \( (-?\d+) (-?\d+) \) (\w+)", comp):
        master = m.group(2)
        if "corner" in master:
            continue
        x, y, orient = int(m.group(3)) / 1000, int(m.group(4)) / 1000, m.group(5)
        if y == 0:
            side = "S"
        elif x == 0:
            side = "W"
        else:
            side = "N" if die_h - y < die_w - x else "E"
        have[(master, side, round(x if side in "NS" else y, 3), orient)] += 1
    missing = want - have
    extra = have - want
    seam = [k for k in extra.elements() if k[0] == gen.GPIO_MASTER and k[1] in "NS"
            and k[3] == gen.SIDE_ORIENT[k[1]]]
    other = list((extra - collections.Counter(seam)).elements())
    for k in list(missing.elements())[:6]:
        errors.append(f"pad missing at the openframe's place: {k}")
    for k in other[:6]:
        errors.append(f"pad not placed as in the openframe: {k}")
    if len(seam) != 4:
        errors.append(f"expected 4 seam GPIO pads, found {len(seam)}")
    print(f"pads: {sum(have.values())} pad cells, {sum((want & have).values())} at the "
          f"openframe's position and orientation, {len(seam)} seam pads")

    for e in errors:
        print("  " + e)
    print("PASS" if not errors else f"FAIL ({len(errors)} problem(s))")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
