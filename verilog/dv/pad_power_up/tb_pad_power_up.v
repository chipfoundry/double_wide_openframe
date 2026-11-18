// SPDX-FileCopyrightText: 2026 ChipFoundry
// SPDX-License-Identifier: Apache-2.0
//
// Pad power-up test for the double-wide padframe (power-aware RTL, sky130 pad
// behavioural models).
//
// The frame drives every GPIO pad's ENABLE_H / ENABLE_VDDA_H (and the reset
// pad's ENABLE_H) from the power-on reset porb_h, as the caravel openframe
// does. While porb_h is low the pad must hold its safe state - output driver
// off - whatever its 1.8 V controls say, including when 1.8 V is not up yet.
//
// Sequence (simple_por's model releases porb_h 500 ns after vddio rises):
//   t=100   3.3 V up (vddio, vdda*), 1.8 V off      -> all 63 pads must be Z
//   t=350   1.8 V up (vccd, vccd1, vccd2)           -> still Z (porb_h low)
//   ~t=600  porb_h releases                         -> pads drive gpio_out
//   t=900   every pad drives i % 2 and reads it back on gpio_in
//
// With +late_1v8 the 1.8 V supplies come up only after porb_h has released
// (t=900). The test then reports how many pads are undriven / X in the gap:
// this is the documented limit of a 3.3 V-only POR (see docs/datasheet.md),
// shared with the openframe, and is reported, not failed.
`timescale 1 ns / 1 ps
`default_nettype none

module tb_pad_power_up;
    localparam N = 63;

    reg vddio = 1'b0, vdda = 1'b0, vdda1 = 1'b0, vdda2 = 1'b0;
    reg vccd = 1'b0, vccd1 = 1'b0, vccd2 = 1'b0;
    reg vss = 1'b0;

    wire [N-1:0] gpio;
    wire resetb = 1'b1;

    // Supplies are driven one-way into the (multi-bond) power pad buses.
    wire [0:0] vccd_pad  = vccd;
    wire [0:0] vccd1_pad = vccd1;
    wire [0:0] vccd2_pad = vccd2;
    wire [1:0] vdda_pad  = {2{vdda}};
    wire [1:0] vdda1_pad = {2{vdda1}};
    wire [0:0] vdda2_pad = vdda2;
    wire [1:0] vddio_pad = {2{vddio}};
    wire [1:0] vssa_pad  = {2{vss}};
    wire [2:0] vssa1_pad = {3{vss}};
    wire [0:0] vssa2_pad = vss;
    wire [1:0] vssd_pad  = {2{vss}};
    wire [0:0] vssd1_pad = vss;
    wire [0:0] vssd2_pad = vss;
    wire [3:0] vssio_pad = {4{vss}};

    double_wide_chip_io uut (
        .gpio_pad   (gpio),
        .resetb_pad (resetb),
        .vccd_pad   (vccd_pad),
        .vccd1_pad  (vccd1_pad),
        .vccd2_pad  (vccd2_pad),
        .vdda_pad   (vdda_pad),
        .vdda1_pad  (vdda1_pad),
        .vdda2_pad  (vdda2_pad),
        .vddio_pad  (vddio_pad),
        .vssa_pad   (vssa_pad),
        .vssa1_pad  (vssa1_pad),
        .vssa2_pad  (vssa2_pad),
        .vssd_pad   (vssd_pad),
        .vssd1_pad  (vssd1_pad),
        .vssd2_pad  (vssd2_pad),
        .vssio_pad  (vssio_pad)
    );

    integer errors = 0;
    integer i, nz, nx, n0, n1;
    reg late_1v8;

    task count_pads;
        begin
            nz = 0; nx = 0; n0 = 0; n1 = 0;
            for (i = 0; i < N; i = i + 1) begin
                case (gpio[i])
                    1'bz: nz = nz + 1;
                    1'bx: nx = nx + 1;
                    1'b0: n0 = n0 + 1;
                    1'b1: n1 = n1 + 1;
                endcase
            end
        end
    endtask

    task expect_all_z(input [8*40-1:0] what);
        begin
            count_pads;
            $display("[%0t] %0s: porb_h=%b  pads Z=%0d X=%0d 0=%0d 1=%0d",
                     $time, what, uut.porb_h, nz, nx, n0, n1);
            for (i = 0; i < N; i = i + 1)
                if (gpio[i] !== 1'bz) begin
                    $display("  FAIL gpio[%0d] = %b, expected Z (pad must be undriven while porb_h is low)",
                             i, gpio[i]);
                    errors = errors + 1;
                end
        end
    endtask

    task expect_driving(input [8*40-1:0] what);
        begin
            count_pads;
            $display("[%0t] %0s: porb_h=%b  pads Z=%0d X=%0d 0=%0d 1=%0d",
                     $time, what, uut.porb_h, nz, nx, n0, n1);
            for (i = 0; i < N; i = i + 1) begin
                if (gpio[i] !== (i % 2)) begin
                    $display("  FAIL gpio[%0d] = %b, expected %0d", i, gpio[i], i % 2);
                    errors = errors + 1;
                end
                if (uut.gpio_in[i] !== (i % 2)) begin
                    $display("  FAIL gpio_in[%0d] = %b, expected %0d", i, uut.gpio_in[i], i % 2);
                    errors = errors + 1;
                end
            end
        end
    endtask

    initial begin
        late_1v8 = $test$plusargs("late_1v8");
`ifdef WAVE_GEN
        $dumpfile("tb_pad_power_up.vcd");
        $dumpvars(0, tb_pad_power_up);
`endif
        #100;
        vddio = 1'b1; vdda = 1'b1; vdda1 = 1'b1; vdda2 = 1'b1;   // 3.3 V up
        #200;
        if (uut.porb_h !== 1'b0) begin
            $display("  FAIL porb_h = %b before the POR delay, expected 0", uut.porb_h);
            errors = errors + 1;
        end
        expect_all_z("3.3V up, 1.8V off");

        if (!late_1v8) begin
            #50;
            vccd = 1'b1; vccd1 = 1'b1; vccd2 = 1'b1;              // 1.8 V up
            #100;
            expect_all_z("1.8V up, POR active");
            #450;
            if (uut.porb_h !== 1'b1) begin
                $display("  FAIL porb_h = %b after the POR delay, expected 1", uut.porb_h);
                errors = errors + 1;
            end
            expect_driving("POR released");
        end else begin
            #450;
            count_pads;
            $display("[%0t] INFO late 1.8V (known limit): porb_h=%b  pads Z=%0d X=%0d 0=%0d 1=%0d",
                     $time, uut.porb_h, nz, nx, n0, n1);
            #50;
            vccd = 1'b1; vccd1 = 1'b1; vccd2 = 1'b1;
            #100;
            expect_driving("1.8V up after POR");
        end

        if (errors == 0) $display("PASS");
        else $display("FAIL: %0d error(s)", errors);
        $finish;
    end
endmodule
`default_nettype wire
