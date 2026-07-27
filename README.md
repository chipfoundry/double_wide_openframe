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
`xres_buf`, `constant_block`). GPIO pad enables use local
`TIE_HI_ESD`/`TIE_LO_ESD` (the reset pad still uses `porb_h`). Power is the
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

See [`signoff/README.md`](signoff/README.md) for the latest results. Known open
item: **38× metal2 spacing (m2.2)** on the north edge from KLayout BEOL.

LVS config: [`lvs/double_wide_chip_io/lvs_config.json`](lvs/double_wide_chip_io/lvs_config.json).

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
verilog/rtl/  double_wide_chip_io.v                       generated padframe (chip top)
              double_wide_openframe_project_wrapper.v      generated empty wrapper
              __double_wide_openframe_project_wrapper.v    precheck port golden
              dw_defines.vh                                generated pad-count define
librelane/padframe/  config.yaml pad_cfg.tcl pad_pos.tcl pdn_cfg.tcl chip.sdc
librelane/wrapper/   config.json pin_template.def         empty-wrapper harden
lvs/                 padframe LVS config for cf-precheck
signoff/             DRC/LVS reports
flake.nix Makefile   LibreLane 3 environment + orchestration
```
