// SPDX-FileCopyrightText: 2026 ChipFoundry
// SPDX-License-Identifier: Apache-2.0
//
// Simulation defines for the double-wide openframe harness. caravel_cocotb
// forwards every `define in a *defines.v file to cocotb as a plusarg;
// OpenFrame_env reads OPENFRAME_IO_PADS from there.

`ifndef DW_OPENFRAME_DEFINES_V
`define DW_OPENFRAME_DEFINES_V

`define OPENFRAME_IO_PADS 63

`endif
