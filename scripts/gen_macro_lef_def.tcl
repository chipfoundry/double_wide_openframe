# Regenerate a macro's abstract LEF and its DEF view from its GDS using Magic.
#
# Invoked by scripts/regen_macro_views.py, which passes parameters via env vars:
#   MACRO_CELL    - top cell name (reads gds/<cell>.gds)
#   MACRO_OUT_LEF - raw LEF output path
#   MACRO_OUT_DEF - DEF output path
#
#   magic -dnull -noconsole \
#       -rcfile $PDK_ROOT/$PDK/libs.tech/magic/$PDK.magicrc \
#       scripts/gen_macro_lef_def.tcl

set cell    $env(MACRO_CELL)
set out_lef $env(MACRO_OUT_LEF)
set out_def $env(MACRO_OUT_DEF)

gds read gds/$cell.gds
load $cell
select top cell

# Abstract LEF: ports become PINs, everything else becomes OBS.
lef write $out_lef -hide

# DEF geometry view.
def write $out_def

puts "MAGIC_DONE $cell"
exit 0
