# Double Wide Openframe (padframe / harness)

A **double-wide** sky130 openframe **padframe**, generated with **LibreLane 3**
(the `Chip` flow, as in `sky130-fabulous-testchip`).

This repo is the **caravel-style harness**: it generates and hardens the
double-wide pad ring and provides the **empty user-area wrapper pin template**.
The user's actual design lives in a separate, `openframe_user_project`-style
repo: **`../dw_openframe_user_project`**. Harden the wrapper there, then
cell-swap it into the frame here with `make integrate`.

It is the same idea as the caravel openframe — an empty user area surrounded by a
pad ring, where the user builds their design inside the area, connects to the
boundary pins, and we cell-swap their hardened block into the full padframe — but
**twice as wide**:

- **Left (West)** and **right (East)** sides are **exactly the same as openframe**.
- **Top (North)** and **bottom (South)** rows are the **openframe rows duplicated**
  side by side across the doubled width (continuous rows, only 4 outer corners).

## GPIO count

The double-wide therefore has **more GPIOs than openframe's 44**:

| Side | Openframe | Double-wide | |
|------|-----------|-------------|---|
| West (left)  | 14 | **14** | same as openframe |
| East (right) | 15 | **15** | same as openframe |
| North (top)  | 9  | **20** | openframe x2 + 2 mid-seam |
| South (bottom)| 6 | **14** | openframe x2 + 2 mid-seam |
| **Total**    | 44 | **63** | |

Die: **7176 x 5188 um** (`2 x 3588` wide, height unchanged).
User area (`double_wide_openframe_project_wrapper`): **6754.63 x 4766.63 um**.

## How it is built

Everything below is generated from the real caravel openframe layout, so pad
cells, positions, ordering, the 63-GPIO index map, RTL and LibreLane pad tables
can never drift:

```
scripts/extract_openframe_pads.py
  parses ../caravel/mag/chip_io_openframe.mag
  -> verilog/rtl/double_wide_chip_io.v                    (padframe RTL)
  -> verilog/rtl/double_wide_openframe_project_wrapper.v  (empty user wrapper)
  -> verilog/rtl/dw_defines.vh                            (DW_OPENFRAME_IO_PADS = 63)
  -> librelane/padframe/config.yaml + pad_pos.tcl + pad_lists.yaml
  -> librelane/wrapper/pin_template.def                   (wrapper pin template)
  -> pad_summary.json                                     (per-pad index/side/domain map)
```

The padframe is a **pass-through GPIO ring** (no management SoC / user-id
block): each GPIO pad's control signals route straight to the user-area
boundary (openframe-style `gpio_in/out/oeb/inp_dis/ib_mode_sel/vtrip_sel/
slow_sel/holdover/analog_en/sel/pol/dm0-2/analog_io/analog_noesd_io/in_h`).
Openframe-style **POR / reset** is retained (`simple_por`, south `xres4v2`,
`xres_buf`, `constant_block`). As in the openframe, every GPIO pad's
`ENABLE_H` / `ENABLE_VDDA_H` and the reset pad's `ENABLE_H` follow `porb_h`, so
the pads stay in their safe state until the POR releases; `porb_h` reaches them
over a hand-drawn met1 loop around the user area (`Padframe.PorbRing`). The
other pad controls (`HLD_H_N`, `ENABLE_INP_H`, `ENABLE_VSWITCH_H`) use the pad's
local `TIE_HI_ESD`/`TIE_LO_ESD`, also as in the openframe. Power is the
**preserved openframe multi-domain** structure (user0 bottom, user1
right/top, user2 left), with top/bottom clamps duplicated across the doubled
width.

Technical datasheet (catalog): [`docs/`](docs/).

## Flow

```bash
# 0. one-time: PDK
make enable-pdk

# 1. (re)generate all pad artifacts from the caravel openframe
make pads

# 2. harden the EMPTY user-area wrapper (pin template)      -> build/wrapper/
nix develop --command make wrapper-empty

# 3. harden the double-wide padframe (places+routes wrapper)-> build/padframe/
nix develop --command make padframe

# 4. cell-swap a user wrapper GDS into the padframe         -> build/double_wide_openframe.gds
#    (harden the user design in ../dw_openframe_user_project first)
nix develop --command make integrate \
    USER_GDS=../dw_openframe_user_project/gds/double_wide_openframe_project_wrapper.gds
```

`make padframe` consumes the empty-wrapper LEF/GDS/nl produced in step 2, so run
the wrapper harden first.

## Golden assets for cf-precheck

When running precheck on a user project, pass **this repo** as `-c` (golden root):

```bash
cf-precheck -i ../dw_openframe_user_project -p $PDK_ROOT/sky130A -c .
# or: make -C ../dw_openframe_user_project precheck
```

Required golden files (also refreshed by `make publish-golden` after `wrapper-empty`):

| Path | Purpose |
|------|---------|
| `gds/double_wide_openframe_project_wrapper_empty.gds` | XOR golden empty wrapper |
| `verilog/rtl/__double_wide_openframe_project_wrapper.v` | Port-list golden |

## Padframe DRC / LVS (cf-precheck scripts)

```bash
export PYTHONPATH=../cf-precheck/src:/usr/lib/klayout/pymod:$PYTHONPATH
make drc-klayout          # KLayout FEOL/BEOL/… → signoff/padframe_drc/
make drc-magic            # Magic drc(full) (slow; noisy on IO macros)
make lvs-padframe         # needs netgen + magic on PATH
```

With the cf-precheck decks, all six KLayout checks (FEOL, BEOL, offgrid,
metal/CA density, pin-label purposes, zero-area) pass on the current padframe
GDS.

LVS config: [`lvs/double_wide_chip_io/lvs_config.json`](lvs/double_wide_chip_io/lvs_config.json).

## Pad enables (`porb_h`)

As in `chip_io_openframe.v`, `porb_h` drives `ENABLE_H` and `ENABLE_VDDA_H` on
all 63 GPIO pads and `ENABLE_H` on the reset pad. The router does not do this
fan-out: `Padframe.PorbRing` ([`librelane/padframe/porb_ring.py`](librelane/padframe/porb_ring.py))
draws it before global routing, the same way the openframe layout does. It
draws a closed 0.26 um met1 loop around the user area at the openframe offset
(209.33 um from the die edge, pushed just far enough inward on a side where a
fixed cell is in the way). Each enable pin gets a via1 plus a met2 stub to the
loop, and a met1 patch joins the loop to the `porb_h` metal that `simple_por`
already brings out to the wrapper pin. `porb_h` stays SPECIAL, so TritonRoute
routes around this wiring. The step checks every shape against the fixed
met1/met2 around it and stops instead of drawing a short.

The padframe router is also kept out of the user area. The empty wrapper's LEF
has no obstructions, so without this TritonRoute jogs padframe nets along the
inside of the wrapper edge, where they short to a hardened user design's own
edge routing. `ROUTING_OBSTRUCTIONS` blocks met1-met5 over the wrapper, open only
around each wrapper pin the router has to reach. There are no exceptions:
`lef/constant_block.lef` lists the block's real met2/met3 shapes
(`scripts/exact_macro_obs.py`) instead of solid obstructions, so the router has
a straight lane from each `constant_block` to its two loopback pins and does
not need to jog inside the user area.

```bash
make check-pad-enables  # RTL: pad control pins driven exactly as in the openframe
make check-porb-net     # GDS: porb_h is one net over simple_por, the wrapper pin
                        #      and all 127 enable pins; no TIE_HI_ESD on it
make sim-power-up       # sim: pads stay undriven until porb_h releases
make check-xres-loops      # GDS: the reset pad's three local nets are whole and separate
make check-analog-domains  # GDS: vdda/vdda1/vdda2 and vssa/vssa1/vssa2 are six nets
make check-clamp-links     # GDS: vccd/vccd1/vccd2 and vssd/vssd1/vssd2 are whole and separate
```

## Building a user project

The user design lives in **`../dw_openframe_user_project`** (the
`openframe_user_project`-style repo). Replace the body of
`double_wide_openframe_project_wrapper` with your design — keeping the **module
name and port list identical** — harden it there, then `make integrate` with your
GDS. `pad_summary.json` documents which physical pad each `gpio[*]` index maps to,
and the wrapper's pin locations are fixed by `librelane/wrapper/pin_template.def`.

## Documentation

Catalog datasheet (geometry, pinout, power, GPIO/reset, integration):

- [`docs/datasheet.md`](docs/datasheet.md)
- [`docs/pinout.md`](docs/pinout.md)

## Layout

```
docs/      datasheet + pinout + SVG figures
scripts/   extract_openframe_pads.py   generator (source of truth)
           gen_datasheet_figures.py    datasheet SVG / pinout tables
           integrate_openframe.tcl     Magic cell-swap
           run_padframe_drc.py         cf-precheck Magic/KLayout DRC
           run_padframe_lvs.py         cf-precheck LVS wrapper
           check_pad_enables.py        pad enable drivers vs chip_io_openframe.v
           porb_probe_points.py        pin probe points for check_porb_net.py
           check_porb_net.py           KLayout porb_h connectivity check on GDS
verilog/rtl/  double_wide_chip_io.v                       generated padframe (chip top)
              double_wide_openframe_project_wrapper.v      generated empty wrapper
              __double_wide_openframe_project_wrapper.v    precheck port golden
              dw_defines.vh                                generated pad-count define
verilog/dv/pad_power_up/  pad power-up (porb_h) testbench, iverilog
librelane/padframe/  config.yaml pad_cfg.tcl pad_pos.tcl pdn_cfg.tcl chip.sdc
                     padframe_steps.py + porb_ring.py, bridge_*.py, reset_special_nets.py
librelane/wrapper/   config.json pin_template.def         empty-wrapper harden
lvs/                 padframe LVS config for cf-precheck
signoff/             DRC/LVS reports
flake.nix Makefile   LibreLane 3 environment + orchestration
```
