# Double Wide Openframe padframe (harness) - build orchestration
#
# This repo is the caravel-style *harness*: it generates and hardens the
# double-wide pad ring and provides the empty user-area wrapper pin template.
# The user's actual design lives in the sibling ../dw_openframe_user_project
# repo (openframe_user_project-style). The flow mirrors the caravel openframe
# "empty frame + cell swap" model, with the LibreLane 3 Chip flow (as in
# sky130-fabulous-testchip).
#
#   1. make pads              -> regenerate the pad tables from the caravel openframe
#   2. make wrapper-empty     -> harden the EMPTY user-area wrapper (pin template)
#   3. make padframe          -> harden the double-wide padframe (places empty wrapper)
#   4. make integrate         -> cell-swap a user wrapper GDS into the padframe
#
PDK        ?= sky130A
PDK_ROOT   ?= $(HOME)/.ciel
PDK_COMMIT ?= 74c0e6b118a67d94c24172143d3bd597473fa63d

CARAVEL_MAG ?= ../caravel/mag/chip_io_openframe.mag

# RAM notes (this box has only ~15 GiB):
#  * We do NOT wrap librelane in a `systemd-run --scope` / cgroup memory cap:
#    OpenROAD (run via nix) deadlocks inside a memory-limited cgroup here, so a
#    hard cap hangs the flow instead of protecting it.
#  * Instead, peak memory is kept low *by design*: the empty user-area wrapper is
#    hardened elaborate-only with fill/tap/CTS/resizer/antenna/diode disabled
#    (see librelane/wrapper/config.json), so it never fills the ~32 mm^2 die with
#    millions of cells. Peak RSS for the empty wrapper is ~2.5 GiB.
#  * Also keep run artifacts out of the flake dir (see .gitignore); otherwise
#    `nix develop` copies gigabytes of runs/ into the nix store on every call.
#
# NOTE: run `make enable-pdk` once. Use --manual-pdk like sky130-fabulous-testchip.
LIBRELANE = librelane --pdk-root $(PDK_ROOT) --pdk $(PDK) --manual-pdk

.PHONY: all pads wrapper-empty padframe integrate clean \
        padframe-klayout padframe-openroad enable-pdk

all: pads wrapper-empty padframe

enable-pdk:
	ciel enable $(PDK_COMMIT) --pdk-family $(PDK)

## Regenerate pad coordinate tables + PAD_* lists + RTL pad counts from the
## caravel openframe layout.
pads:
	python3 scripts/extract_openframe_pads.py \
		--mag $(CARAVEL_MAG) \
		--out-tcl librelane/padframe/pad_pos.tcl \
		--out-yaml librelane/padframe/pad_lists.yaml \
		--out-json pad_summary.json \
		--out-rtl verilog/rtl/double_wide_chip_io.v \
		--out-wrapper verilog/rtl/double_wide_openframe_project_wrapper.v \
		--out-defines verilog/rtl/dw_defines.vh \
		--out-config librelane/padframe/config.yaml \
		--out-pad-blackboxes verilog/rtl/pad_ef_io_blackboxes.v \
		--out-def-template librelane/wrapper/pin_template.def

## Harden the empty user-area wrapper (produces the LEF/DEF/GDS pin template).
wrapper-empty:
	$(LIBRELANE) librelane/wrapper/config.json --save-views-to build/wrapper/

## Harden the double-wide padframe (Chip flow). Requires wrapper-empty first.
padframe:
	$(LIBRELANE) librelane/padframe/config.yaml --save-views-to build/padframe/

padframe-klayout:
	$(LIBRELANE) librelane/padframe/config.yaml --last-run --flow OpenInKLayout

padframe-openroad:
	$(LIBRELANE) librelane/padframe/config.yaml --last-run --flow OpenInOpenROAD

## Cell-swap a hardened user wrapper GDS into the padframe frame.
## The user design is hardened in the sibling ../dw_openframe_user_project repo;
## point USER_GDS at its hardened wrapper GDS, e.g.:
##   make integrate USER_GDS=../dw_openframe_user_project/gds/double_wide_openframe_project_wrapper.gds
## Defaults to the empty pin-template wrapper produced by `make wrapper-empty`.
USER_GDS ?= build/wrapper/gds/double_wide_openframe_project_wrapper.gds
integrate:
	PADFRAME_GDS=build/padframe/gds/double_wide_chip_io.gds \
	USER_WRAPPER_GDS=$(USER_GDS) \
	OUT_GDS=build/double_wide_openframe.gds \
	magic -dnull -noconsole -rcfile $(PDK_ROOT)/$(PDK)/libs.tech/magic/$(PDK).magicrc \
		scripts/integrate_openframe.tcl

clean:
	rm -rf build runs
