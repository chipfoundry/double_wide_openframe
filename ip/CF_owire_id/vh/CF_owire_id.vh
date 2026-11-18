(* blackbox, keep *)
// Default cell for the harness. The blackbox attribute makes Yosys ignore
// the assigns and keep the macro; Icarus simulates the pass-through. The
// GDS carries the same shorts on met3. Replacing the GDS at tapeout with
// the reset mux must keep this port list and the LEF pin coordinates.
// chip_reset_n, mask_rev, and gpio_in_pin are unused in this default cell.
module CF_owire_id (
`ifdef USE_POWER_PINS
    inout VPWR,
    inout VGND,
`endif
    input        chip_reset_n,
    input [31:0] mask_rev,
    input        gpio_in_pin,
    input        gpio_out_user,
    output       gpio_out_pin,
    input        gpio_oeb_user,
    output       gpio_oeb_pin,
    input        gpio_inp_dis_user,
    output       gpio_inp_dis_pin,
    input        gpio_ib_mode_sel_user,
    output       gpio_ib_mode_sel_pin,
    input        gpio_vtrip_sel_user,
    output       gpio_vtrip_sel_pin,
    input        gpio_slow_sel_user,
    output       gpio_slow_sel_pin,
    input        gpio_holdover_user,
    output       gpio_holdover_pin,
    input        gpio_analog_en_user,
    output       gpio_analog_en_pin,
    input        gpio_analog_sel_user,
    output       gpio_analog_sel_pin,
    input        gpio_analog_pol_user,
    output       gpio_analog_pol_pin,
    input        gpio_dm0_user,
    output       gpio_dm0_pin,
    input        gpio_dm1_user,
    output       gpio_dm1_pin,
    input        gpio_dm2_user,
    output       gpio_dm2_pin
);
    assign gpio_out_pin = gpio_out_user;
    assign gpio_oeb_pin = gpio_oeb_user;
    assign gpio_inp_dis_pin = gpio_inp_dis_user;
    assign gpio_ib_mode_sel_pin = gpio_ib_mode_sel_user;
    assign gpio_vtrip_sel_pin = gpio_vtrip_sel_user;
    assign gpio_slow_sel_pin = gpio_slow_sel_user;
    assign gpio_holdover_pin = gpio_holdover_user;
    assign gpio_analog_en_pin = gpio_analog_en_user;
    assign gpio_analog_sel_pin = gpio_analog_sel_user;
    assign gpio_analog_pol_pin = gpio_analog_pol_user;
    assign gpio_dm0_pin = gpio_dm0_user;
    assign gpio_dm1_pin = gpio_dm1_user;
    assign gpio_dm2_pin = gpio_dm2_user;
endmodule
