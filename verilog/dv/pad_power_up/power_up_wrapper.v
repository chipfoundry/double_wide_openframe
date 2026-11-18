// SPDX-FileCopyrightText: 2026 ChipFoundry
// SPDX-License-Identifier: Apache-2.0
//
// Test-only stand-in for double_wide_openframe_project_wrapper (same ports).
// Configures every pad as a strong push-pull output (dm = 3'b110, oeb = 0)
// driving gpio_out[i] = i % 2, with the input buffer enabled.
//
// Like real 1.8 V core logic, its outputs are only valid while the 1.8 V
// supplies are up: with vccd / vccd1 / vccd2 missing every control is X. That
// is the situation the pad enables (porb_h) must protect against.
`default_nettype none
module double_wide_openframe_project_wrapper (
`ifdef USE_POWER_PINS
    inout vddio, vssio, vccd, vssd, vdda, vssa,
    inout vdda1, vssa1, vccd1, vssd1,
    inout vdda2, vssa2, vccd2, vssd2,
`endif
    input  porb_h,
    input  por_l,
    input  porb_l,
    input  resetb_h,
    input  resetb_l,
    input  [31:0] mask_rev,
    input  [62:0] gpio_in,
    input  [62:0] gpio_in_h,
    input  [62:0] gpio_loopback_one,
    input  [62:0] gpio_loopback_zero,
    output [62:0] gpio_out,
    output [62:0] gpio_oeb,
    output [62:0] gpio_inp_dis,
    output [62:0] gpio_ib_mode_sel,
    output [62:0] gpio_vtrip_sel,
    output [62:0] gpio_slow_sel,
    output [62:0] gpio_holdover,
    output [62:0] gpio_analog_en,
    output [62:0] gpio_analog_sel,
    output [62:0] gpio_analog_pol,
    output [62:0] gpio_dm0,
    output [62:0] gpio_dm1,
    output [62:0] gpio_dm2,
    inout  [62:0] analog_io,
    inout  [62:0] analog_noesd_io
);
`ifdef USE_POWER_PINS
    wire core_on = (vccd === 1'b1) && (vccd1 === 1'b1) && (vccd2 === 1'b1) &&
                   (vssd === 1'b0) && (vssd1 === 1'b0) && (vssd2 === 1'b0);
`else
    wire core_on = 1'b1;
`endif
    // 1.8 V logic output: the intended value when powered, X otherwise.
    // (Plain ternaries, not a function: a continuous assign through a function
    // would not re-evaluate when core_on changes.)
    localparam [62:0] ALT = 63'h2AAA_AAAA_AAAA_AAAA;  // gpio_out[i] = i % 2
    localparam [62:0] X63 = {63{1'bx}};

    assign gpio_out         = core_on ? ALT : X63;
    assign gpio_oeb         = core_on ? 63'b0 : X63;         // output enabled
    assign gpio_inp_dis     = core_on ? 63'b0 : X63;         // input buffer on
    assign gpio_ib_mode_sel = core_on ? 63'b0 : X63;
    assign gpio_vtrip_sel   = core_on ? 63'b0 : X63;
    assign gpio_slow_sel    = core_on ? 63'b0 : X63;
    assign gpio_holdover    = core_on ? 63'b0 : X63;
    assign gpio_analog_en   = core_on ? 63'b0 : X63;
    assign gpio_analog_sel  = core_on ? 63'b0 : X63;
    assign gpio_analog_pol  = core_on ? 63'b0 : X63;
    assign gpio_dm0         = core_on ? 63'b0 : X63;         // dm = 3'b110: strong push-pull
    assign gpio_dm1         = core_on ? {63{1'b1}} : X63;
    assign gpio_dm2         = core_on ? {63{1'b1}} : X63;
endmodule
`default_nettype wire
