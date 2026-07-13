// Golden port-list template for double_wide_openframe_project_wrapper.
// Used by cf-precheck consistency / documentation when -c points at dw_openframe.
// Keep ports identical to verilog/rtl/double_wide_openframe_project_wrapper.v.

`default_nettype none

module double_wide_openframe_project_wrapper (
`ifdef USE_POWER_PINS
    inout vddio, vssio, vccd, vssd, vdda, vssa,
    inout vdda1, vssa1, vccd1, vssd1,
    inout vdda2, vssa2, vccd2, vssd2,
`endif
    input  [58:0] gpio_in,
    input  [58:0] gpio_in_h,
    output [58:0] gpio_out,
    output [58:0] gpio_oeb,
    output [58:0] gpio_inp_dis,
    output [58:0] gpio_ib_mode_sel,
    output [58:0] gpio_vtrip_sel,
    output [58:0] gpio_slow_sel,
    output [58:0] gpio_holdover,
    output [58:0] gpio_analog_en,
    output [58:0] gpio_analog_sel,
    output [58:0] gpio_analog_pol,
    output [58:0] gpio_dm0,
    output [58:0] gpio_dm1,
    output [58:0] gpio_dm2,
    inout  [58:0] analog_io,
    inout  [58:0] analog_noesd_io
);

endmodule

`default_nettype wire
