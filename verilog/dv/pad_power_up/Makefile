# Pad power-up test: pads must stay undriven until porb_h releases.
#   make            # run (needs iverilog + the sky130A PDK)
#   make late_1v8   # 1.8 V after POR release: reports the known limit
PDK_ROOT ?= $(HOME)/.ciel
PDK      ?= sky130A
LIB      := $(PDK_ROOT)/$(PDK)/libs.ref
RTL      := ../../rtl

SRCS := \
	$(LIB)/sky130_fd_io/verilog/sky130_fd_io.v \
	$(LIB)/sky130_fd_io/verilog/sky130_ef_io.v \
	$(LIB)/sky130_fd_sc_hd/verilog/primitives.v \
	$(LIB)/sky130_fd_sc_hd/verilog/sky130_fd_sc_hd.v \
	$(LIB)/sky130_fd_sc_hvl/verilog/primitives.v \
	$(LIB)/sky130_fd_sc_hvl/verilog/sky130_fd_sc_hvl.v \
	$(RTL)/simple_por.v \
	$(RTL)/constant_block.v \
	$(RTL)/xres_buf.v \
	$(RTL)/dw_branding_stubs.v \
	$(RTL)/double_wide_chip_io.v \
	power_up_wrapper.v \
	tb_pad_power_up.v

DEFS := -DFUNCTIONAL -DUSE_POWER_PINS -DSIM -DUNIT_DELAY=\#1

.PHONY: all run late_1v8 clean
all: run

tb_pad_power_up.vvp: $(SRCS)
	iverilog -g2012 -Wno-timescale $(DEFS) -s tb_pad_power_up -o $@ $(SRCS)

run: tb_pad_power_up.vvp
	vvp -n $< | tee run.log
	@grep -q '^PASS' run.log

late_1v8: tb_pad_power_up.vvp
	vvp -n $< +late_1v8 | tee run_late_1v8.log
	@grep -q '^PASS' run_late_1v8.log

clean:
	rm -f tb_pad_power_up.vvp run.log run_late_1v8.log tb_pad_power_up.vcd
