(* keep *)
// Physical blackbox. The GDS is the unprogrammed sky130 user-id cell;
// tapeout via-programs it. mask_rev is left open in the padframe.
module user_id_programming (
`ifdef USE_POWER_PINS
    inout VPWR,
    inout VGND,
`endif
    output [31:0] mask_rev
);
endmodule
