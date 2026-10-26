// SPDX-FileCopyrightText: 2026 ChipFoundry
// SPDX-License-Identifier: Apache-2.0
//
// caravel_cocotb testbench top for the double-wide openframe harness
// (`cf verify` runs caravel_cocotb with --openframe against this file).
// The OpenFrame_env API addresses pads through the flat gpioN / gpioN_en /
// gpioN_monitor nets below; iverilog cannot drive single elements of a
// vector from cocotb, so they must stay as individual wires.

`timescale 1 ns / 1 ps
`include "includes.v"

module caravel_top;

`ifdef WAVE_GEN
initial begin
`ifdef VCS
    $vcdplusfile("waves.vpd");
    $vcdpluson();
`else
    $dumpfile("waves.vcd");
    $dumpvars(0, caravel_top);
`endif
end
`endif

    reg  vddio_tb;
    reg  vssio_tb;
    reg  vdda_tb;
    reg  vssa_tb;
    reg  vccd_tb;
    reg  vssd_tb;
    reg  vdda1_tb;
    reg  vdda2_tb;
    reg  vssa1_tb;
    reg  vssa2_tb;
    reg  vccd1_tb;
    reg  vccd2_tb;
    reg  vssd1_tb;
    reg  vssd2_tb;

    // OpenFrame_env times the test from clock_tb. The double-wide frame has no
    // dedicated clock pad (user clocks come in on GPIOs), so it is only
    // referenced here to keep Icarus from pruning it.
    reg  clock_tb;
    wire clock_tb_ref = clock_tb;
    wire resetb_tb;

    wire [`OPENFRAME_IO_PADS-1:0] mprj_io_tb;

    // Supplies are driven one-way into the (multi-bond) power pad buses.
    wire [0:0] vccd_pad   = vccd_tb;
    wire [0:0] vccd1_pad  = vccd1_tb;
    wire [0:0] vccd2_pad  = vccd2_tb;
    wire [1:0] vdda_pad   = {2{vdda_tb}};
    wire [1:0] vdda1_pad  = {2{vdda1_tb}};
    wire [0:0] vdda2_pad  = vdda2_tb;
    wire [1:0] vddio_pad  = {2{vddio_tb}};
    wire [1:0] vssa_pad   = {2{vssa_tb}};
    wire [2:0] vssa1_pad  = {3{vssa1_tb}};
    wire [0:0] vssa2_pad  = vssa2_tb;
    wire [1:0] vssd_pad   = {2{vssd_tb}};
    wire [0:0] vssd1_pad  = vssd1_tb;
    wire [0:0] vssd2_pad  = vssd2_tb;
    wire [3:0] vssio_pad  = {4{vssio_tb}};

    double_wide_chip_io uut (
        .gpio_pad   (mprj_io_tb),
        .resetb_pad (resetb_tb),
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

`ifdef USE_USER_VIP
    `USER_VIP
`endif

    // Testbench-side pad drivers (driven from cocotb via OpenFrame_env.drive_gpio)
    wire gpio0;
    wire gpio0_en;
    wire gpio1;
    wire gpio1_en;
    wire gpio2;
    wire gpio2_en;
    wire gpio3;
    wire gpio3_en;
    wire gpio4;
    wire gpio4_en;
    wire gpio5;
    wire gpio5_en;
    wire gpio6;
    wire gpio6_en;
    wire gpio7;
    wire gpio7_en;
    wire gpio8;
    wire gpio8_en;
    wire gpio9;
    wire gpio9_en;
    wire gpio10;
    wire gpio10_en;
    wire gpio11;
    wire gpio11_en;
    wire gpio12;
    wire gpio12_en;
    wire gpio13;
    wire gpio13_en;
    wire gpio14;
    wire gpio14_en;
    wire gpio15;
    wire gpio15_en;
    wire gpio16;
    wire gpio16_en;
    wire gpio17;
    wire gpio17_en;
    wire gpio18;
    wire gpio18_en;
    wire gpio19;
    wire gpio19_en;
    wire gpio20;
    wire gpio20_en;
    wire gpio21;
    wire gpio21_en;
    wire gpio22;
    wire gpio22_en;
    wire gpio23;
    wire gpio23_en;
    wire gpio24;
    wire gpio24_en;
    wire gpio25;
    wire gpio25_en;
    wire gpio26;
    wire gpio26_en;
    wire gpio27;
    wire gpio27_en;
    wire gpio28;
    wire gpio28_en;
    wire gpio29;
    wire gpio29_en;
    wire gpio30;
    wire gpio30_en;
    wire gpio31;
    wire gpio31_en;
    wire gpio32;
    wire gpio32_en;
    wire gpio33;
    wire gpio33_en;
    wire gpio34;
    wire gpio34_en;
    wire gpio35;
    wire gpio35_en;
    wire gpio36;
    wire gpio36_en;
    wire gpio37;
    wire gpio37_en;
    wire gpio38;
    wire gpio38_en;
    wire gpio39;
    wire gpio39_en;
    wire gpio40;
    wire gpio40_en;
    wire gpio41;
    wire gpio41_en;
    wire gpio42;
    wire gpio42_en;
    wire gpio43;
    wire gpio43_en;
    wire gpio44;
    wire gpio44_en;
    wire gpio45;
    wire gpio45_en;
    wire gpio46;
    wire gpio46_en;
    wire gpio47;
    wire gpio47_en;
    wire gpio48;
    wire gpio48_en;
    wire gpio49;
    wire gpio49_en;
    wire gpio50;
    wire gpio50_en;
    wire gpio51;
    wire gpio51_en;
    wire gpio52;
    wire gpio52_en;
    wire gpio53;
    wire gpio53_en;
    wire gpio54;
    wire gpio54_en;
    wire gpio55;
    wire gpio55_en;
    wire gpio56;
    wire gpio56_en;
    wire gpio57;
    wire gpio57_en;
    wire gpio58;
    wire gpio58_en;
    wire gpio59;
    wire gpio59_en;
    wire gpio60;
    wire gpio60_en;
    wire gpio61;
    wire gpio61_en;
    wire gpio62;
    wire gpio62_en;

    assign mprj_io_tb[0] = (gpio0_en) ? gpio0 : 1'bz;
    assign mprj_io_tb[1] = (gpio1_en) ? gpio1 : 1'bz;
    assign mprj_io_tb[2] = (gpio2_en) ? gpio2 : 1'bz;
    assign mprj_io_tb[3] = (gpio3_en) ? gpio3 : 1'bz;
    assign mprj_io_tb[4] = (gpio4_en) ? gpio4 : 1'bz;
    assign mprj_io_tb[5] = (gpio5_en) ? gpio5 : 1'bz;
    assign mprj_io_tb[6] = (gpio6_en) ? gpio6 : 1'bz;
    assign mprj_io_tb[7] = (gpio7_en) ? gpio7 : 1'bz;
    assign mprj_io_tb[8] = (gpio8_en) ? gpio8 : 1'bz;
    assign mprj_io_tb[9] = (gpio9_en) ? gpio9 : 1'bz;
    assign mprj_io_tb[10] = (gpio10_en) ? gpio10 : 1'bz;
    assign mprj_io_tb[11] = (gpio11_en) ? gpio11 : 1'bz;
    assign mprj_io_tb[12] = (gpio12_en) ? gpio12 : 1'bz;
    assign mprj_io_tb[13] = (gpio13_en) ? gpio13 : 1'bz;
    assign mprj_io_tb[14] = (gpio14_en) ? gpio14 : 1'bz;
    assign mprj_io_tb[15] = (gpio15_en) ? gpio15 : 1'bz;
    assign mprj_io_tb[16] = (gpio16_en) ? gpio16 : 1'bz;
    assign mprj_io_tb[17] = (gpio17_en) ? gpio17 : 1'bz;
    assign mprj_io_tb[18] = (gpio18_en) ? gpio18 : 1'bz;
    assign mprj_io_tb[19] = (gpio19_en) ? gpio19 : 1'bz;
    assign mprj_io_tb[20] = (gpio20_en) ? gpio20 : 1'bz;
    assign mprj_io_tb[21] = (gpio21_en) ? gpio21 : 1'bz;
    assign mprj_io_tb[22] = (gpio22_en) ? gpio22 : 1'bz;
    assign mprj_io_tb[23] = (gpio23_en) ? gpio23 : 1'bz;
    assign mprj_io_tb[24] = (gpio24_en) ? gpio24 : 1'bz;
    assign mprj_io_tb[25] = (gpio25_en) ? gpio25 : 1'bz;
    assign mprj_io_tb[26] = (gpio26_en) ? gpio26 : 1'bz;
    assign mprj_io_tb[27] = (gpio27_en) ? gpio27 : 1'bz;
    assign mprj_io_tb[28] = (gpio28_en) ? gpio28 : 1'bz;
    assign mprj_io_tb[29] = (gpio29_en) ? gpio29 : 1'bz;
    assign mprj_io_tb[30] = (gpio30_en) ? gpio30 : 1'bz;
    assign mprj_io_tb[31] = (gpio31_en) ? gpio31 : 1'bz;
    assign mprj_io_tb[32] = (gpio32_en) ? gpio32 : 1'bz;
    assign mprj_io_tb[33] = (gpio33_en) ? gpio33 : 1'bz;
    assign mprj_io_tb[34] = (gpio34_en) ? gpio34 : 1'bz;
    assign mprj_io_tb[35] = (gpio35_en) ? gpio35 : 1'bz;
    assign mprj_io_tb[36] = (gpio36_en) ? gpio36 : 1'bz;
    assign mprj_io_tb[37] = (gpio37_en) ? gpio37 : 1'bz;
    assign mprj_io_tb[38] = (gpio38_en) ? gpio38 : 1'bz;
    assign mprj_io_tb[39] = (gpio39_en) ? gpio39 : 1'bz;
    assign mprj_io_tb[40] = (gpio40_en) ? gpio40 : 1'bz;
    assign mprj_io_tb[41] = (gpio41_en) ? gpio41 : 1'bz;
    assign mprj_io_tb[42] = (gpio42_en) ? gpio42 : 1'bz;
    assign mprj_io_tb[43] = (gpio43_en) ? gpio43 : 1'bz;
    assign mprj_io_tb[44] = (gpio44_en) ? gpio44 : 1'bz;
    assign mprj_io_tb[45] = (gpio45_en) ? gpio45 : 1'bz;
    assign mprj_io_tb[46] = (gpio46_en) ? gpio46 : 1'bz;
    assign mprj_io_tb[47] = (gpio47_en) ? gpio47 : 1'bz;
    assign mprj_io_tb[48] = (gpio48_en) ? gpio48 : 1'bz;
    assign mprj_io_tb[49] = (gpio49_en) ? gpio49 : 1'bz;
    assign mprj_io_tb[50] = (gpio50_en) ? gpio50 : 1'bz;
    assign mprj_io_tb[51] = (gpio51_en) ? gpio51 : 1'bz;
    assign mprj_io_tb[52] = (gpio52_en) ? gpio52 : 1'bz;
    assign mprj_io_tb[53] = (gpio53_en) ? gpio53 : 1'bz;
    assign mprj_io_tb[54] = (gpio54_en) ? gpio54 : 1'bz;
    assign mprj_io_tb[55] = (gpio55_en) ? gpio55 : 1'bz;
    assign mprj_io_tb[56] = (gpio56_en) ? gpio56 : 1'bz;
    assign mprj_io_tb[57] = (gpio57_en) ? gpio57 : 1'bz;
    assign mprj_io_tb[58] = (gpio58_en) ? gpio58 : 1'bz;
    assign mprj_io_tb[59] = (gpio59_en) ? gpio59 : 1'bz;
    assign mprj_io_tb[60] = (gpio60_en) ? gpio60 : 1'bz;
    assign mprj_io_tb[61] = (gpio61_en) ? gpio61 : 1'bz;
    assign mprj_io_tb[62] = (gpio62_en) ? gpio62 : 1'bz;

    // Pad monitors (read from cocotb via OpenFrame_env.monitor_gpio)
    wire gpio0_monitor;
    wire gpio1_monitor;
    wire gpio2_monitor;
    wire gpio3_monitor;
    wire gpio4_monitor;
    wire gpio5_monitor;
    wire gpio6_monitor;
    wire gpio7_monitor;
    wire gpio8_monitor;
    wire gpio9_monitor;
    wire gpio10_monitor;
    wire gpio11_monitor;
    wire gpio12_monitor;
    wire gpio13_monitor;
    wire gpio14_monitor;
    wire gpio15_monitor;
    wire gpio16_monitor;
    wire gpio17_monitor;
    wire gpio18_monitor;
    wire gpio19_monitor;
    wire gpio20_monitor;
    wire gpio21_monitor;
    wire gpio22_monitor;
    wire gpio23_monitor;
    wire gpio24_monitor;
    wire gpio25_monitor;
    wire gpio26_monitor;
    wire gpio27_monitor;
    wire gpio28_monitor;
    wire gpio29_monitor;
    wire gpio30_monitor;
    wire gpio31_monitor;
    wire gpio32_monitor;
    wire gpio33_monitor;
    wire gpio34_monitor;
    wire gpio35_monitor;
    wire gpio36_monitor;
    wire gpio37_monitor;
    wire gpio38_monitor;
    wire gpio39_monitor;
    wire gpio40_monitor;
    wire gpio41_monitor;
    wire gpio42_monitor;
    wire gpio43_monitor;
    wire gpio44_monitor;
    wire gpio45_monitor;
    wire gpio46_monitor;
    wire gpio47_monitor;
    wire gpio48_monitor;
    wire gpio49_monitor;
    wire gpio50_monitor;
    wire gpio51_monitor;
    wire gpio52_monitor;
    wire gpio53_monitor;
    wire gpio54_monitor;
    wire gpio55_monitor;
    wire gpio56_monitor;
    wire gpio57_monitor;
    wire gpio58_monitor;
    wire gpio59_monitor;
    wire gpio60_monitor;
    wire gpio61_monitor;
    wire gpio62_monitor;

    assign gpio0_monitor = mprj_io_tb[0];
    assign gpio1_monitor = mprj_io_tb[1];
    assign gpio2_monitor = mprj_io_tb[2];
    assign gpio3_monitor = mprj_io_tb[3];
    assign gpio4_monitor = mprj_io_tb[4];
    assign gpio5_monitor = mprj_io_tb[5];
    assign gpio6_monitor = mprj_io_tb[6];
    assign gpio7_monitor = mprj_io_tb[7];
    assign gpio8_monitor = mprj_io_tb[8];
    assign gpio9_monitor = mprj_io_tb[9];
    assign gpio10_monitor = mprj_io_tb[10];
    assign gpio11_monitor = mprj_io_tb[11];
    assign gpio12_monitor = mprj_io_tb[12];
    assign gpio13_monitor = mprj_io_tb[13];
    assign gpio14_monitor = mprj_io_tb[14];
    assign gpio15_monitor = mprj_io_tb[15];
    assign gpio16_monitor = mprj_io_tb[16];
    assign gpio17_monitor = mprj_io_tb[17];
    assign gpio18_monitor = mprj_io_tb[18];
    assign gpio19_monitor = mprj_io_tb[19];
    assign gpio20_monitor = mprj_io_tb[20];
    assign gpio21_monitor = mprj_io_tb[21];
    assign gpio22_monitor = mprj_io_tb[22];
    assign gpio23_monitor = mprj_io_tb[23];
    assign gpio24_monitor = mprj_io_tb[24];
    assign gpio25_monitor = mprj_io_tb[25];
    assign gpio26_monitor = mprj_io_tb[26];
    assign gpio27_monitor = mprj_io_tb[27];
    assign gpio28_monitor = mprj_io_tb[28];
    assign gpio29_monitor = mprj_io_tb[29];
    assign gpio30_monitor = mprj_io_tb[30];
    assign gpio31_monitor = mprj_io_tb[31];
    assign gpio32_monitor = mprj_io_tb[32];
    assign gpio33_monitor = mprj_io_tb[33];
    assign gpio34_monitor = mprj_io_tb[34];
    assign gpio35_monitor = mprj_io_tb[35];
    assign gpio36_monitor = mprj_io_tb[36];
    assign gpio37_monitor = mprj_io_tb[37];
    assign gpio38_monitor = mprj_io_tb[38];
    assign gpio39_monitor = mprj_io_tb[39];
    assign gpio40_monitor = mprj_io_tb[40];
    assign gpio41_monitor = mprj_io_tb[41];
    assign gpio42_monitor = mprj_io_tb[42];
    assign gpio43_monitor = mprj_io_tb[43];
    assign gpio44_monitor = mprj_io_tb[44];
    assign gpio45_monitor = mprj_io_tb[45];
    assign gpio46_monitor = mprj_io_tb[46];
    assign gpio47_monitor = mprj_io_tb[47];
    assign gpio48_monitor = mprj_io_tb[48];
    assign gpio49_monitor = mprj_io_tb[49];
    assign gpio50_monitor = mprj_io_tb[50];
    assign gpio51_monitor = mprj_io_tb[51];
    assign gpio52_monitor = mprj_io_tb[52];
    assign gpio53_monitor = mprj_io_tb[53];
    assign gpio54_monitor = mprj_io_tb[54];
    assign gpio55_monitor = mprj_io_tb[55];
    assign gpio56_monitor = mprj_io_tb[56];
    assign gpio57_monitor = mprj_io_tb[57];
    assign gpio58_monitor = mprj_io_tb[58];
    assign gpio59_monitor = mprj_io_tb[59];
    assign gpio60_monitor = mprj_io_tb[60];
    assign gpio61_monitor = mprj_io_tb[61];
    assign gpio62_monitor = mprj_io_tb[62];

endmodule
