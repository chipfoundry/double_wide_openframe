# AUTO-GENERATED pad cell positions (um) for the double-wide ring: the low
# end of each pad cell along its row, taken from the caravel openframe
# layout (north and south twice, the right-hand copy 3588 um on).
set caravel_pad_pos [dict create]

dict set caravel_pad_pos PAD_SOUTH "\
    394.000 \
    663.000 \
    932.000 \
    1206.000 \
    1475.000 \
    1749.000 \
    2023.000 \
    2297.000 \
    2571.000 \
    2845.000 \
    3114.000 \
    3385.000 \
    3659.000 \
    3982.000 \
    4520.000 \
    4794.000 \
    5063.000 \
    5337.000 \
    5611.000 \
    5885.000 \
    6159.000 \
    6433.000 \
    6702.000 \
"

dict set caravel_pad_pos PAD_EAST "\
    500.000 \
    726.000 \
    951.000 \
    1177.000 \
    1402.000 \
    1627.000 \
    1853.000 \
    2078.000 \
    2299.000 \
    2519.000 \
    2739.000 \
    2965.000 \
    3190.000 \
    3416.000 \
    3641.000 \
    3866.000 \
    4092.000 \
    4312.000 \
    4538.000 \
    4758.000 \
"

dict set caravel_pad_pos PAD_NORTH "\
    381.000 \
    638.000 \
    895.000 \
    1152.000 \
    1410.000 \
    1667.000 \
    1919.000 \
    2364.000 \
    2621.000 \
    2878.000 \
    3130.000 \
    3387.000 \
    3644.000 \
    3969.000 \
    4226.000 \
    4483.000 \
    4740.000 \
    4998.000 \
    5255.000 \
    5507.000 \
    5952.000 \
    6209.000 \
    6466.000 \
    6718.000 \
"

dict set caravel_pad_pos PAD_WEST "\
    340.000 \
    551.000 \
    908.000 \
    1124.000 \
    1340.000 \
    1556.000 \
    1772.000 \
    1988.000 \
    2204.000 \
    2415.000 \
    2626.000 \
    2842.000 \
    3058.000 \
    3274.000 \
    3490.000 \
    3706.000 \
    3922.000 \
    4138.000 \
    4349.000 \
    4560.000 \
    4771.000 \
"

# Analog power cuts: row, low coordinate along the edge (um), instance.
set analog_cuts {
    {IO_NORTH 1742.000 disconnect_vdda_n}
    {IO_WEST 831.000 disconnect_vdda_w}
    {IO_EAST 349.000 disconnect_vdda_e}
}
