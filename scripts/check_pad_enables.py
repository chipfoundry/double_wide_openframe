#!/usr/bin/env python3
"""Check that every pad control pin is driven like the caravel openframe.

Elaborates the double-wide padframe RTL and the caravel openframe
chip_io_openframe.v with yosys (pad / POR / constant cells as blackboxes),
classifies the driver of each GPIO and reset-pad control pin, and compares the
two frames pin by pin:

    porb_h          simple_por porb_h output
    TIE_HI_ESD      the pad's own TIE_HI_ESD
    TIE_LO_ESD      the pad's own TIE_LO_ESD
    const.one       a constant_block `one` output
    wrapper         a user-wrapper signal (gpio_out[i], ...)

Every GPIO pad in each frame must show the same mapping, and the two frames must
agree, otherwise the script exits non-zero. Needs yosys on PATH (nix develop).

    python3 scripts/check_pad_enables.py [--caravel ../caravel]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

GPIO_CELL = "sky130_ef_io__gpiov2_pad"
XRES_CELL = "sky130_fd_io__top_xres4v2"
GPIO_PINS = ("ENABLE_H", "ENABLE_VDDA_H", "HLD_H_N", "ENABLE_INP_H",
             "ENABLE_VSWITCH_H", "ENABLE_VDDIO")
XRES_PINS = ("ENABLE_H", "ENABLE_VDDIO")
# Pins whose driver must be the power-on reset (the point of this check).
MUST_BE_PORB = {GPIO_CELL: ("ENABLE_H", "ENABLE_VDDA_H"), XRES_CELL: ("ENABLE_H",)}

BLACKBOXES = [
    os.path.join(ROOT, "verilog/rtl/pad_ef_io_blackboxes.v"),
    os.path.join(ROOT, "verilog/rtl/por_reset_blackboxes.v"),
]
# Openframe-only cells that are not in the double-wide blackbox files.
EXTRA_BB = """
(* blackbox *) module user_id_programming #(parameter USER_PROJECT_ID = 0)
    (inout VPWR, inout VGND, output [31:0] mask_rev);
endmodule
(* blackbox *) module sky130_ef_io__disconnect_vdda_slice_5um(
    inout AMUXBUS_A, AMUXBUS_B, VSSA, VDDA, VSWITCH, VDDIO_Q, VCCHIB, VDDIO,
    VCCD, VSSIO, VSSD, VSSIO_Q);
endmodule
"""


def elaborate(top, sources, defines, workdir):
    out = os.path.join(workdir, f"{top}.json")
    bb = os.path.join(workdir, "extra_bb.v")
    with open(bb, "w") as f:
        f.write(EXTRA_BB)
    dflags = " ".join(f"-D{d}" for d in defines)
    script = "; ".join(
        [f"read_verilog -sv -lib {dflags} {b}" for b in BLACKBOXES + [bb]]
        + [f"read_verilog -sv {dflags} {' '.join(sources)}",
           f"hierarchy -top {top}", "proc", "flatten -noscopeinfo",
           f"write_json {out}"]
    )
    r = subprocess.run(["yosys", "-q", "-p", script], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"yosys failed for {top}:\n{r.stdout}\n{r.stderr}")
    with open(out) as f:
        return json.load(f)["modules"][top]


def classify(mod):
    """{cell_name: (cell_type, {pin: driver_class})} for the pad cells."""
    driver = {}  # bit -> (cell, port)
    for cname, cell in mod["cells"].items():
        for port, bits in cell["connections"].items():
            if cell.get("port_directions", {}).get(port) == "output" or (
                    cell["type"] in (GPIO_CELL, XRES_CELL)
                    and port in ("TIE_HI_ESD", "TIE_LO_ESD")) or (
                    cell["type"] == "constant_block" and port in ("one", "zero")) or (
                    cell["type"] == "simple_por" and port in ("porb_h", "porb_l", "por_l")):
                for b in bits:
                    if isinstance(b, int):
                        driver[b] = (cname, cell["type"], port)
    names = {}
    for n, info in mod["netnames"].items():
        for b in info["bits"]:
            if isinstance(b, int) and (b not in names or len(n) < len(names[b])):
                names[b] = n

    out = {}
    for cname, cell in mod["cells"].items():
        ctype = cell["type"]
        if ctype not in (GPIO_CELL, XRES_CELL):
            continue
        pins = GPIO_PINS if ctype == GPIO_CELL else XRES_PINS
        res = {}
        for pin in pins:
            bits = cell["connections"].get(pin, [])
            if not bits:
                res[pin] = "unconnected"
                continue
            b = bits[0]
            if not isinstance(b, int):
                res[pin] = f"const {b}"
                continue
            d = driver.get(b)
            if d is None:
                res[pin] = "wrapper" if names.get(b, "").startswith("gpio") else f"net {names.get(b)}"
            elif d[1] == "simple_por":
                res[pin] = d[2]
            elif d[1] == "constant_block":
                res[pin] = f"const.{d[2]}"
            elif d[0] == cname:
                res[pin] = d[2]
            else:
                res[pin] = f"{d[2]} of {d[0]}"
        out[cname] = (ctype, res)
    return out


def summarize(label, pads):
    print(f"== {label}")
    ok = True
    for ctype in (GPIO_CELL, XRES_CELL):
        maps = Counter(tuple(sorted(r.items())) for t, r in pads.values() if t == ctype)
        n = sum(maps.values())
        print(f"  {ctype}: {n} pads, {len(maps)} distinct mapping(s)")
        for m, k in maps.items():
            print(f"    x{k}: " + ", ".join(f"{p}={v}" for p, v in m))
        for name, (t, r) in sorted(pads.items()):
            if t != ctype:
                continue
            for pin in MUST_BE_PORB[ctype]:
                if r.get(pin) != "porb_h":
                    print(f"  FAIL {name}.{pin} = {r.get(pin)} (expected porb_h)")
                    ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--caravel", default=os.path.join(ROOT, "..", "caravel"))
    args = ap.parse_args()
    cv = os.path.abspath(args.caravel)

    with tempfile.TemporaryDirectory() as tmp:
        dw = classify(elaborate(
            "double_wide_chip_io",
            [os.path.join(ROOT, "verilog/rtl/dw_branding_stubs.v"),
             os.path.join(ROOT, "verilog/rtl/double_wide_openframe_project_wrapper.v"),
             os.path.join(ROOT, "verilog/rtl/double_wide_chip_io.v")],
            ["USE_POWER_PINS"], tmp))
        of = classify(elaborate(
            "chip_io_openframe",
            [os.path.join(cv, "verilog/rtl/defines.v"),
             os.path.join(cv, "verilog/rtl/pads.v"),
             os.path.join(cv, "verilog/rtl/chip_io_openframe.v")],
            ["USE_POWER_PINS"], tmp))

    ok = summarize("double_wide_chip_io", dw)
    ok &= summarize("chip_io_openframe (reference)", of)

    for ctype in (GPIO_CELL, XRES_CELL):
        dw_maps = {tuple(sorted(r.items())) for t, r in dw.values() if t == ctype}
        of_maps = {tuple(sorted(r.items())) for t, r in of.values() if t == ctype}
        if dw_maps != of_maps:
            print(f"FAIL {ctype}: double-wide mapping(s) {sorted(dw_maps)} "
                  f"!= openframe {sorted(of_maps)}")
            ok = False
    n_gpio = sum(1 for t, _ in dw.values() if t == GPIO_CELL)
    n_porb = sum(1 for t, r in dw.values() for p, v in r.items()
                 if v == "porb_h" and p in MUST_BE_PORB[t])
    print(f"double-wide: {n_gpio} GPIO pads, {n_porb} enable pins on porb_h")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
