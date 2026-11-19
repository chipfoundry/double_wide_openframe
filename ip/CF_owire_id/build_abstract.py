#!/usr/bin/env python3
"""Write the CF_owire_id pin contract: Verilog, LEF, and pass-through GDS.

The harness routes to these pins. The default GDS shorts each user control
to its pad pin, so GPIO 0 works when the tapeout swap is not applied. The
swap (run_shadow_fill.py --replace CF_owire_id=<gds>) must keep this pin
list, these coordinates, and this origin.

West-edge pins face the core. Control pairs are two met3 pins stacked 1.2 um
apart and covered by one met3 rectangle. mask_rev, chip_reset_n, and
gpio_in_pin are inputs with no internal metal beyond the pin. VPWR/VGND are
met1 landings; the default cell has no devices.
"""

import gzip
import os

import klayout.db as pya

W_UM = 155.0
H_UM = 240.0
PIN_DEPTH_UM = 2.0
PIN_W_UM = 0.30
PAIR_PITCH_UM = 6.0
PAIR_GAP_UM = 1.20  # from the bottom of the user pin to the bottom of the pad pin
PAIR_Y0_UM = 8.0
SINGLE_Y0_UM = 90.0
SINGLE_PITCH_UM = 4.0

CTRLS = (
    "gpio_out", "gpio_oeb", "gpio_inp_dis", "gpio_ib_mode_sel", "gpio_vtrip_sel",
    "gpio_slow_sel", "gpio_holdover", "gpio_analog_en", "gpio_analog_sel",
    "gpio_analog_pol", "gpio_dm0", "gpio_dm1", "gpio_dm2",
)

HERE = os.path.dirname(os.path.abspath(__file__))


def _pair_ys(i):
    user_y = PAIR_Y0_UM + i * PAIR_PITCH_UM
    pad_y = user_y + PAIR_GAP_UM + PIN_W_UM
    return user_y, pad_y


def pins():
    """(name, direction, use, layer, x1, y1, x2, y2) in microns."""
    out = []
    for i, sig in enumerate(CTRLS):
        user_y, pad_y = _pair_ys(i)
        out.append((f"{sig}_user", "INPUT", "SIGNAL", "met3",
                    0.0, user_y, PIN_DEPTH_UM, user_y + PIN_W_UM))
        out.append((f"{sig}_pin", "OUTPUT", "SIGNAL", "met3",
                    0.0, pad_y, PIN_DEPTH_UM, pad_y + PIN_W_UM))
    singles = ["chip_reset_n", "gpio_in_pin"] + [f"mask_rev[{i}]" for i in range(32)]
    for k, name in enumerate(singles):
        y = SINGLE_Y0_UM + k * SINGLE_PITCH_UM
        out.append((name, "INPUT", "SIGNAL", "met3",
                    0.0, y, PIN_DEPTH_UM, y + PIN_W_UM))
    out.append(("VPWR", "INOUT", "POWER", "met1", 0.0, 228.0, PIN_DEPTH_UM, 229.5))
    out.append(("VGND", "INOUT", "GROUND", "met1", 0.0, 232.5, PIN_DEPTH_UM, 234.0))
    return out


def _check(plist):
    if plist[-1][6] > H_UM or max(p[4] for p in plist) > W_UM:
        raise RuntimeError("a pin falls outside the cell")
    # Different met3 pins on different nets must not overlap. A control pair
    # overlaps on purpose: the user pin, the pad pin, and the short are one net.
    metals = []
    for name, _d, use, layer, x1, y1, x2, y2 in plist:
        if layer != "met3":
            continue
        net = name[:-5] if name.endswith("_user") or name.endswith("_pin") else name
        # gpio_in_pin ends with _pin but is not a control pair
        if name == "gpio_in_pin":
            net = name
        metals.append((net, y1, y2))
    metals.sort(key=lambda t: t[1])
    for (n0, _a, b0), (n1, a1, _b) in zip(metals, metals[1:]):
        if b0 > a1 + 1e-9 and n0 != n1:
            raise RuntimeError(f"met3 overlap between {n0} and {n1}")


OBS_X0_UM = 2.5


def write_lef(plist, path):
    lines = [
        "VERSION 5.7 ;",
        "  NOWIREEXTENSIONATPIN ON ;",
        '  DIVIDERCHAR "/" ;',
        '  BUSBITCHARS "[]" ;',
        "MACRO CF_owire_id",
        "  CLASS BLOCK ;",
        "  FOREIGN CF_owire_id ;",
        "  ORIGIN 0.000 0.000 ;",
        f"  SIZE {W_UM:.3f} BY {H_UM:.3f} ;",
    ]
    for name, direction, use, layer, x1, y1, x2, y2 in plist:
        lines += [
            f"  PIN {name}",
            f"    DIRECTION {direction} ;",
            f"    USE {use} ;",
            "    PORT",
            f"      LAYER {layer} ;",
            f"        RECT {x1:.3f} {y1:.3f} {x2:.3f} {y2:.3f} ;",
            "    END",
            f"  END {name}",
        ]
    # The block is empty, so without this the router treats its interior as
    # open space and runs wires through it (gpio_holdover[0] left the block on
    # met4 and shorted the pad-ring rails). Keep the west 2.5 um open: all pins
    # sit on the west edge, 0..2 um.
    lines += ["  OBS"]
    for layer in ("met1", "met2", "met3", "met4"):
        lines += [
            f"    LAYER {layer} ;",
            f"      RECT {OBS_X0_UM:.3f} 0.000 {W_UM:.3f} {H_UM:.3f} ;",
        ]
    lines += ["  END", "END CF_owire_id", "END LIBRARY", ""]
    with open(path, "w") as fh:
        fh.write("\n".join(lines))


def write_vh(path):
    ports = [
        "`ifdef USE_POWER_PINS",
        "    inout VPWR,",
        "    inout VGND,",
        "`endif",
        "    input        chip_reset_n,",
        "    input [31:0] mask_rev,",
        "    input        gpio_in_pin,",
    ]
    assigns = []
    for sig in CTRLS:
        ports.append(f"    input        {sig}_user,")
        ports.append(f"    output       {sig}_pin,")
        assigns.append(f"    assign {sig}_pin = {sig}_user;")
    ports[-1] = ports[-1].rstrip(",")
    body = "\n".join(assigns)
    text = f"""(* blackbox, keep *)
// Default cell for the harness. The blackbox attribute makes Yosys ignore
// the assigns and keep the macro; Icarus simulates the pass-through. The
// GDS carries the same shorts on met3. Replacing the GDS at tapeout with
// the reset mux must keep this port list and the LEF pin coordinates.
// chip_reset_n, mask_rev, and gpio_in_pin are unused in this default cell.
module CF_owire_id (
{os.linesep.join(ports)}
);
{body}
endmodule
"""
    with open(path, "w") as fh:
        fh.write(text)


def write_gds(plist, path):
    layout = pya.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("CF_owire_id")
    boundary = layout.layer(235, 4)
    met3 = layout.layer(70, 20)
    met1 = layout.layer(68, 20)
    top.shapes(boundary).insert(pya.DBox(0, 0, W_UM, H_UM))
    drawn = set()
    for name, _d, _u, layer, x1, y1, x2, y2 in plist:
        if layer == "met1":
            top.shapes(met1).insert(pya.DBox(x1, y1, x2, y2))
            continue
        if name.endswith("_user") and name != "gpio_in_pin":
            sig = name[:-5]
            if sig in CTRLS and sig not in drawn:
                user_y, pad_y = _pair_ys(CTRLS.index(sig))
                top.shapes(met3).insert(
                    pya.DBox(0.0, user_y, PIN_DEPTH_UM, pad_y + PIN_W_UM))
                drawn.add(sig)
            continue
        if name.endswith("_pin") and name != "gpio_in_pin":
            continue
        top.shapes(met3).insert(pya.DBox(x1, y1, x2, y2))
    raw = os.path.splitext(path)[0]  # drop one suffix; path ends in .gds.gz
    if raw.endswith(".gds"):
        gds_path = raw
    else:
        gds_path = path[: -len(".gz")] if path.endswith(".gz") else path + ".gds"
    layout.write(gds_path)
    with open(gds_path, "rb") as fh:
        data = fh.read()
    os.remove(gds_path)
    with gzip.open(path, "wb") as fh:
        fh.write(data)


def main():
    plist = pins()
    _check(plist)
    write_lef(plist, os.path.join(HERE, "lef", "CF_owire_id.lef"))
    write_vh(os.path.join(HERE, "vh", "CF_owire_id.vh"))
    write_gds(plist, os.path.join(HERE, "gds", "CF_owire_id.gds.gz"))
    print(f"wrote {len(plist)} pins")


if __name__ == "__main__":
    main()
