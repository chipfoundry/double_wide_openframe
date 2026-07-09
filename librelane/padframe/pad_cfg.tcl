# Double-wide openframe pad ring placement.
#
# Adapted from LibreLane's default padring script and the sky130-fabulous-testchip
# pad_cfg.tcl. Bond-pad-center coordinates come from the AUTO-GENERATED
# pad_pos.tcl (extracted from the caravel openframe layout, left/right kept
# exact, top/bottom duplicated). Only 4 outer corners are placed; the top and
# bottom rows are continuous (filler bridges the middle seam).

source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections

puts "\[INFO\] Generating double-wide padring..."

set block [ord::get_db_block]
set units [$block getDefUnits]

set DIE_HEIGHT [expr {[lindex $::env(DIE_AREA) 3] - [lindex $::env(DIE_AREA) 1]}]
set DIE_WIDTH  [expr {[lindex $::env(DIE_AREA) 2] - [lindex $::env(DIE_AREA) 0]}]

set pad_site        [pad::find_site $::env(PAD_SITE_NAME)]
set pad_corner_site [pad::find_site $::env(PAD_CORNER_SITE_NAME)]

set pad_corner_site_width  [expr double([$pad_corner_site getWidth]) / $units]
set pad_corner_site_height [expr double([$pad_corner_site getHeight]) / $units]

make_io_sites \
    -horizontal_site $::env(PAD_SITE_NAME) \
    -vertical_site $::env(PAD_SITE_NAME) \
    -corner_site $::env(PAD_CORNER_SITE_NAME) \
    -offset $::env(PAD_EDGE_SPACING) \
    -rotation_horizontal $::env(PAD_ROTATION_HORIZONTAL) \
    -rotation_vertical $::env(PAD_ROTATION_VERTICAL) \
    -rotation_corner $::env(PAD_ROTATION_CORNER)

set sides {PAD_SOUTH PAD_EAST PAD_NORTH PAD_WEST}
set row_names [dict create PAD_SOUTH IO_SOUTH PAD_EAST IO_EAST PAD_NORTH IO_NORTH PAD_WEST IO_WEST]

# AUTO-GENERATED bond-pad-center coordinates (defines caravel_pad_pos).
source [file join [file dirname [info script]] pad_pos.tcl]

# gpiov2 pads have a small bondpad offset from the cell center.
set bondpad_offsets [dict create]
dict set bondpad_offsets sky130_ef_io__gpiov2_pad 2.885

foreach side $sides {
    set positions [dict get $caravel_pad_pos $side]
    if {[llength $positions] != [llength $::env($side)]} {
        puts stderr "\[ERROR\] $side: [llength $positions] positions vs [llength $::env($side)] instances"
        exit 1
    }
    for {set i 0} {$i < [llength $positions]} {incr i} {
        set pad_position [lindex $positions $i]
        set inst_name [lindex $::env($side) $i]
        if {[set inst [$block findInst $inst_name]] == "NULL"} {
            puts stderr "\[ERROR\] No instance $inst_name found."
            exit 1
        }
        set master_name [[$inst getMaster] getName]
        set bondpad_offset 0
        if {[dict exists $bondpad_offsets $master_name]} {
            set bondpad_offset [dict get $bondpad_offsets $master_name]
        }
        set width [expr [[$inst getMaster] getWidth] / $units]
        set final_pad_position [expr $pad_position + $bondpad_offset - double($width)/2]
        place_pad -row [dict get $row_names $side] -location $final_pad_position $inst_name -master $master_name
    }
}

# Power-domain bridge slices (VCCHIB<->VCCD, VSWITCH<->VDDIO): 2 per side, near corners.
set slice_master sky130_ef_io__connect_vcchib_vccd_and_vswitch_vddio_slice_20um
place_pad -row IO_SOUTH -location $pad_corner_site_width \
    "vcchib_vccd_and_vswitch_vddio_slices\[0\].u" -master $slice_master
place_pad -row IO_SOUTH -location [expr $DIE_WIDTH - $pad_corner_site_width - 20] \
    "vcchib_vccd_and_vswitch_vddio_slices\[1\].u" -master $slice_master
place_pad -row IO_EAST -location $pad_corner_site_height \
    "vcchib_vccd_and_vswitch_vddio_slices\[2\].u" -master $slice_master
place_pad -row IO_EAST -location [expr $DIE_HEIGHT - $pad_corner_site_height - 20] \
    "vcchib_vccd_and_vswitch_vddio_slices\[3\].u" -master $slice_master
place_pad -row IO_NORTH -location $pad_corner_site_width \
    "vcchib_vccd_and_vswitch_vddio_slices\[5\].u" -master $slice_master
place_pad -row IO_NORTH -location [expr $DIE_WIDTH - $pad_corner_site_width - 20] \
    "vcchib_vccd_and_vswitch_vddio_slices\[4\].u" -master $slice_master
place_pad -row IO_WEST -location $pad_corner_site_height \
    "vcchib_vccd_and_vswitch_vddio_slices\[7\].u" -master $slice_master
place_pad -row IO_WEST -location [expr $DIE_HEIGHT - $pad_corner_site_height - 20] \
    "vcchib_vccd_and_vswitch_vddio_slices\[6\].u" -master $slice_master

puts "\[INFO\] Placing corner cells..."
place_corners $::env(PAD_CORNER)

puts "\[INFO\] Placing filler cells..."
place_io_fill -row IO_NORTH {*}$::env(PAD_FILLERS)
place_io_fill -row IO_SOUTH {*}$::env(PAD_FILLERS)
place_io_fill -row IO_WEST {*}$::env(PAD_FILLERS)
place_io_fill -row IO_EAST {*}$::env(PAD_FILLERS)

puts "\[INFO\] Connecting ring by abutment..."
connect_by_abutment

# Expose each pad's bump (PAD/*_PAD) pin as a top-level routable I/O terminal.
# Without this the bond nets (gpio_pad[*], vccd_pad[*], vdda_pad[*], ...) have no
# geometry on a routing layer and global routing aborts with GRT-0042. The
# master->pin map comes from PAD_PLACE_IO_TERMINALS (overridden in config.yaml
# to also cover the openframe-only clamped3 / vdda / vssa clamps).
if { [info exists ::env(PAD_PLACE_IO_TERMINALS)] } {
    puts "\[INFO\] Placing I/O terminals..."
    foreach side $sides {
        foreach inst_name $::env($side) {
            if { [set inst [$block findInst $inst_name]] == "NULL" } {
                puts stderr "\[ERROR\] No instance $inst_name found."
                exit 1
            }
            set master_name [[$inst getMaster] getName]
            foreach master_pin $::env(PAD_PLACE_IO_TERMINALS) {
                set parts [split $master_pin /]
                if { $master_name == [lindex $parts 0] } {
                    place_io_terminals $inst_name/[lindex $parts 1]
                    break
                }
            }
        }
    }
}

puts "\[INFO\] Removing I/O rows..."
remove_io_rows
