# Double-wide openframe cell-swap integration (Magic), analogous to the caravel
# `make openframe` flow.
#
# Loads the hardened padframe (double_wide_chip_io) and dereferences a user's
# hardened wrapper GDS into the `double_wide_openframe_project_wrapper` cell,
# then streams out the final double_wide_openframe.gds.
#
# Driven by environment variables (see Makefile `integrate` target):
#   PADFRAME_GDS      - hardened padframe GDS (contains an empty wrapper ref)
#   USER_WRAPPER_GDS  - user's hardened wrapper GDS to swap in
#   OUT_GDS           - output path for the merged chip GDS

set padframe_gds $::env(PADFRAME_GDS)
set user_gds     $::env(USER_WRAPPER_GDS)
set out_gds      $::env(OUT_GDS)

gds readonly true
gds rescale false

# Bring in the user's hardened wrapper as the definition of the wrapper cell.
puts "\[INFO\] Reading user wrapper: $user_gds"
gds read $user_gds

# Register the wrapper cell as an abstract with its GDS pointer, so that when we
# load the padframe (which references it by name) the user layout is used.
load double_wide_openframe_project_wrapper
property LEFview true
property GDS_FILE $user_gds

# Read the padframe; -dereference resolves the wrapper reference to the user GDS.
puts "\[INFO\] Reading padframe: $padframe_gds"
gds read $padframe_gds
load double_wide_chip_io -dereference

# Write the merged chip.
puts "\[INFO\] Writing merged chip: $out_gds"
gds write $out_gds

puts "\[INFO\] Done."
exit 0
