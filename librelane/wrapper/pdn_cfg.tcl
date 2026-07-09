# Ring-only PDN for the EMPTY double-wide user-area wrapper (pin template).
#
# Intent: the core area must be completely free of PDN metal -- nothing is ever
# placed or routed under the power grid. Power is delivered solely by a core
# ring placed in the die-to-core margin, entirely OUTSIDE the core area. There
# are deliberately NO internal stripes and NO std-cell rails, so a design later
# dropped into the core has the full core available and taps the ring itself.
#
# Adapted from librelane/scripts/openroad/common/pdn_cfg.tcl (the add_pdn_stripe
# / add_pdn_rail calls are intentionally omitted).

source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections

# Register every secondary power/ground domain (the VDD_NETS/GND_NETS supplies:
# vccd/vccd1/vccd2, vddio, vdda/vdda1/vdda2 and their grounds) so each gets its
# own concentric ring strap.
set secondary []
foreach vdd $::env(VDD_NETS) gnd $::env(GND_NETS) {
    if { $vdd != $::env(VDD_NET)} {
        lappend secondary $vdd
        set db_net [[ord::get_db_block] findNet $vdd]
        if {$db_net == "NULL"} {
            set net [odb::dbNet_create [ord::get_db_block] $vdd]
            $net setSpecial
            $net setSigType "POWER"
        }
    }
    if { $gnd != $::env(GND_NET)} {
        lappend secondary $gnd
        set db_net [[ord::get_db_block] findNet $gnd]
        if {$db_net == "NULL"} {
            set net [odb::dbNet_create [ord::get_db_block] $gnd]
            $net setSpecial
            $net setSigType "GROUND"
        }
    }
}

set_voltage_domain -name CORE -power $::env(VDD_NET) -ground $::env(GND_NET) \
    -secondary_power $secondary

if { $::env(PDN_MULTILAYER) != 1 } {
    throw APPLICATION "Ring-only PDN requires PDN_MULTILAYER to be true."
}

# Expose the ring straps as block power pins (so the padframe can connect to the
# wrapper's supplies) when PDN_ENABLE_PINS is set.
set grid_arg_list [list]
if { $::env(PDN_ENABLE_PINS) } {
    lappend grid_arg_list -pins "$::env(PDN_VERTICAL_LAYER) $::env(PDN_HORIZONTAL_LAYER)"
}

define_pdn_grid \
    -name stdcell_grid \
    -starts_with POWER \
    -voltage_domain CORE \
    {*}$grid_arg_list

# Core ring only. Sized (widths/spacings/offset) + core margin in config.json so
# the full concentric stack lands inside the die and clear of the core area.
set arg_list [list]
append_if_flag arg_list PDN_CORE_RING_ALLOW_OUT_OF_DIE -allow_out_of_die
append_if_flag arg_list PDN_CORE_RING_CONNECT_TO_PADS -connect_to_pads
append_if_exists_argument arg_list PDN_CORE_RING_CONNECT_TO_PAD_LAYERS -connect_to_pad_layers

add_pdn_ring \
    -grid stdcell_grid \
    -layers "$::env(PDN_VERTICAL_LAYER) $::env(PDN_HORIZONTAL_LAYER)" \
    -widths "$::env(PDN_CORE_RING_VWIDTH) $::env(PDN_CORE_RING_HWIDTH)" \
    -spacings "$::env(PDN_CORE_RING_VSPACING) $::env(PDN_CORE_RING_HSPACING)" \
    -core_offset "$::env(PDN_CORE_RING_VOFFSET) $::env(PDN_CORE_RING_HOFFSET)" \
    {*}$arg_list

# Close each net's ring loop at the corners (vertical <-> horizontal).
add_pdn_connect \
    -grid stdcell_grid \
    -layers "$::env(PDN_VERTICAL_LAYER) $::env(PDN_HORIZONTAL_LAYER)"
