# SPDX-FileCopyrightText: 2026 ChipFoundry
# SPDX-License-Identifier: Apache-2.0
#
# PDN configuration for double_wide_openframe_project_wrapper.
#
# The padframe delivers every supply as wide met3 straps that stop at the edge
# of the user area, on the pad-aligned power ports listed in pin_template.def.
# LibreLane's stock PDN builds the met4/met5 grid inside the core area only, so
# on its own nothing reaches those ports. (PDN_ENABLE_PINS only labels the grid
# stripes as pins; it does not route to pin locations.)
#
# This file keeps the stock grid, so every PDN_* variable in config.json works
# as documented, and then ties each power port of the pin template to the
# nearest grid stripes of its net. All of the added metal sits in the margin
# between the die edge and the core area, which the grid leaves empty:
#
#   strap   port layer (met3), as wide as the port, from the die edge inward.
#   bar     runs along the edge from the strap to the chosen stripes, one layer
#           below those stripes: met4 on the east/west edges (stripes are met5),
#           met3 on the north/south edges (stripes are met4). Signal pins are
#           met3 on east/west and met2 on north/south, so they route underneath.
#   stub    extends each chosen stripe from the core edge out over the bar.
#
# Via arrays join strap to bar and bar to stub. The port shapes themselves are
# restored by FP_TEMPLATE_COPY_POWER_PINS in config.json. Everything is drawn
# from the grid that was actually generated, so it follows any change of pitch,
# offset or width. A port that cannot be connected stops the flow, which is
# what happens if a macro or a core ring (PDN_CORE_RING) occupies the margin.

# Stock LibreLane grid (stripes, rails, macro grid).
source $::env(SCRIPTS_DIR)/openroad/common/pdn_cfg.tcl

namespace eval dw_pads {
    # Grid stripes each port is tied to. Fewer are used where neighbouring
    # ports of other nets leave no room.
    variable stripes_per_port 2
    # Bars occupy this band of the core margin, measured from the die edge
    # (bar_start) and back from the core edge (bar_end_gap).
    variable bar_start_um 6.0
    variable bar_end_gap_um 4.0
    # Clearance kept from other nets' metal and from hard macros.
    variable clearance_um 3.0
    # Metal already placed: {net layer x1 y1 x2 y2}. A macro is net "" on
    # layer "*", which blocks every net on every layer.
    variable placed [list]
    # Via arrays already built, by layers and size, and where they were put.
    variable via_cache
    array set via_cache {}
    variable via_sites
    array set via_sites {}
}

# Power ports of the pin template as {net layer x1 y1 x2 y2} in database units.
proc dw_pads::read_template_ports { path dbu } {
    set fh [open $path r]
    set text [read $fh]
    close $fh

    if { ![regexp {UNITS\s+DISTANCE\s+MICRONS\s+(\d+)} $text -> units] } {
        error "$path has no UNITS statement"
    }
    if { $dbu % $units != 0 } {
        error "$path uses $units units per micron, the design uses $dbu"
    }
    set scale [expr { $dbu / $units }]

    set begin [string first "\nPINS" $text]
    set end [string first "\nEND PINS" $text]
    if { $begin < 0 || $end < 0 } {
        error "$path has no PINS section"
    }
    set pins [string range $text $begin $end]

    set ports [list]
    set pin_re {-\s+(\S+)\s+\+\s+NET\s+(\S+)([^;]*);}
    set box_re {LAYER\s+(\S+)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)}
    set place_re {(?:PLACED|FIXED)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\S+)}
    foreach { all pin net body } [regexp -all -inline -- $pin_re $pins] {
        if { ![regexp {USE\s+(POWER|GROUND)} $body] } {
            continue
        }
        # A multi-port pin places each port separately.
        set chunks [split [string map [list "+ PORT" "\x01"] $body] "\x01"]
        foreach chunk $chunks {
            set ox 0
            set oy 0
            if { [regexp $place_re $chunk -> ox oy orient] && $orient ne "N" } {
                error "$path: power pin $pin uses orientation $orient, only N is supported"
            }
            foreach { all layer x1 y1 x2 y2 } [regexp -all -inline -- $box_re $chunk] {
                lappend ports [list $net $layer \
                    [expr { ($ox + $x1) * $scale }] [expr { ($oy + $y1) * $scale }] \
                    [expr { ($ox + $x2) * $scale }] [expr { ($oy + $y2) * $scale }]]
            }
        }
    }
    return $ports
}

# Every special-net shape of the block as {net layer x1 y1 x2 y2}.
proc dw_pads::special_shapes { block } {
    set shapes [list]
    foreach net [$block getNets] {
        if { ![$net isSpecial] } {
            continue
        }
        set name [$net getName]
        foreach swire [$net getSWires] {
            foreach box [$swire getWires] {
                if { [$box isVia] } {
                    continue
                }
                lappend shapes [list $name [[$box getTechLayer] getName] \
                    [$box xMin] [$box yMin] [$box xMax] [$box yMax]]
            }
        }
    }
    return $shapes
}

# Via generate rule between two adjacent routing layers, with its geometry:
# {rule cut_layer cut_w cut_h pitch_x pitch_y enclosure_x enclosure_y}.
proc dw_pads::via_rule { tech lower upper } {
    foreach rule [$tech getViaGenerateRules] {
        if { [$rule getViaLayerRuleCount] != 3 } {
            continue
        }
        set enclosure_x 0
        set enclosure_y 0
        set metals [list]
        set cut_layer ""
        for { set i 0 } { $i < 3 } { incr i } {
            set layer_rule [$rule getViaLayerRule $i]
            set layer [$layer_rule getLayer]
            if { [$layer getType] eq "CUT" } {
                if { ![$layer_rule hasRect] || ![$layer_rule hasSpacing] } {
                    continue
                }
                set cut_layer $layer
                set rect [$layer_rule getRect]
                set cut_w [expr { [$rect xMax] - [$rect xMin] }]
                set cut_h [expr { [$rect yMax] - [$rect yMin] }]
                lassign [$layer_rule getSpacing] pitch_x pitch_y
            } else {
                lappend metals [$layer getName]
                if { [$layer_rule hasEnclosure] } {
                    lassign [$layer_rule getEnclosure] ex ey
                    set enclosure_x [expr { max($enclosure_x, $ex) }]
                    set enclosure_y [expr { max($enclosure_y, $ey) }]
                }
            }
        }
        if { $cut_layer ne "" && [lsort $metals] eq [lsort [list $lower $upper]] } {
            return [list $rule $cut_layer $cut_w $cut_h $pitch_x $pitch_y $enclosure_x $enclosure_y]
        }
    }
    error "the technology has no via generate rule between $lower and $upper"
}

# Join two layers over a rectangle with as many cuts as fit inside it.
proc dw_pads::add_via { block swire lower upper x1 y1 x2 y2 } {
    variable via_cache
    variable via_sites
    set tech [[$block getDataBase] getTech]
    set grid [$tech getManufacturingGrid]
    lassign [via_rule $tech $lower $upper] rule cut_layer cut_w cut_h pitch_x pitch_y enc_x enc_y

    # The same enclosure on every side keeps the array legal on both metals
    # whichever way the rule's enclosures are oriented.
    set enclosure [expr { max($enc_x, $enc_y) }]
    set room_x [expr { $x2 - $x1 - 2 * $enclosure - $cut_w - 2 * $grid }]
    set room_y [expr { $y2 - $y1 - 2 * $enclosure - $cut_h - 2 * $grid }]
    if { $room_x < 0 || $room_y < 0 } {
        error "a [expr { ($x2 - $x1) / 1000.0 }] x [expr { ($y2 - $y1) / 1000.0 }] um crossing\
            is too small for a via between $lower and $upper; widen the grid stripes"
    }
    set columns [expr { $room_x / $pitch_x + 1 }]
    set rows [expr { $room_y / $pitch_y + 1 }]

    set key "$lower,$upper,$columns,$rows"
    if { ![info exists via_cache($key)] } {
        set via [odb::dbVia_create $block "dw_pad_${lower}_${upper}_${columns}x${rows}"]
        $via setViaGenerateRule $rule
        set params [$via getViaParams]
        $params setBottomLayer [$tech findLayer $lower]
        $params setCutLayer $cut_layer
        $params setTopLayer [$tech findLayer $upper]
        $params setXCutSize $cut_w
        $params setYCutSize $cut_h
        $params setXCutSpacing [expr { $pitch_x - $cut_w }]
        $params setYCutSpacing [expr { $pitch_y - $cut_h }]
        $params setXBottomEnclosure $enclosure
        $params setYBottomEnclosure $enclosure
        $params setXTopEnclosure $enclosure
        $params setYTopEnclosure $enclosure
        $params setNumCutCols $columns
        $params setNumCutRows $rows
        $via setViaParams $params
        set via_cache($key) $via
    }
    # Centre on a multiple of twice the grid so odd and even arrays both land
    # on the manufacturing grid.
    set step [expr { 2 * $grid }]
    set x [expr { ($x1 + $x2) / 2 / $step * $step }]
    set y [expr { ($y1 + $y2) / 2 / $step * $step }]
    # The two ports of one pad often share a stripe; one via array is enough.
    if { ![info exists via_sites($key,$x,$y)] } {
        odb::dbSBox_create $swire $via_cache($key) $x $y STRIPE
        set via_sites($key,$x,$y) 1
    }
}

proc dw_pads::overlaps { ax1 ay1 ax2 ay2 bx1 by1 bx2 by2 margin } {
    expr { $ax1 < $bx2 + $margin && $bx1 < $ax2 + $margin
        && $ay1 < $by2 + $margin && $by1 < $ay2 + $margin }
}

# True when one of the shapes {layer x1 y1 x2 y2 margin} would come within its
# margin of a hard macro or of another net's metal.
proc dw_pads::blocked { net shapes } {
    variable placed
    foreach shape $shapes {
        lassign $shape layer x1 y1 x2 y2 margin
        foreach other $placed {
            lassign $other other_net other_layer ox1 oy1 ox2 oy2
            if { $other_net eq $net } {
                continue
            }
            if { $other_layer ne "*" && $other_layer ne $layer } {
                continue
            }
            if { [overlaps $x1 $y1 $x2 $y2 $ox1 $oy1 $ox2 $oy2 $margin] } {
                return 1
            }
        }
    }
    return 0
}

# Map a rectangle from edge coordinates (u along the edge, v inward from the
# die edge) to layout coordinates.
proc dw_pads::place { side die u1 v1 u2 v2 } {
    lassign $die dx1 dy1 dx2 dy2
    switch $side {
        W { return [list [expr { $dx1 + $v1 }] $u1 [expr { $dx1 + $v2 }] $u2] }
        E { return [list [expr { $dx2 - $v2 }] $u1 [expr { $dx2 - $v1 }] $u2] }
        S { return [list $u1 [expr { $dy1 + $v1 }] $u2 [expr { $dy1 + $v2 }]] }
        N { return [list $u1 [expr { $dy2 - $v2 }] $u2 [expr { $dy2 - $v1 }]] }
    }
}

# Draw metal {layer x1 y1 x2 y2 ...} on a net and record it as placed.
proc dw_pads::draw { block net_name swire shapes } {
    variable placed
    set tech [[$block getDataBase] getTech]
    foreach shape $shapes {
        lassign $shape layer x1 y1 x2 y2
        set record [list $net_name $layer $x1 $y1 $x2 $y2]
        if { [lsearch -exact $placed $record] < 0 } {
            odb::dbSBox_create $swire [$tech findLayer $layer] $x1 $y1 $x2 $y2 STRIPE
            lappend placed $record
        }
    }
}

# Draw the strap of one template port and the part of its bar that lies over
# the strap, and list the grid stripes the bar can be extended to. Returns the
# port as a dict for extend_port.
proc dw_pads::start_port { block port shapes } {
    variable bar_start_um
    variable bar_end_gap_um
    variable clearance_um

    lassign $port net_name port_layer px1 py1 px2 py2
    set tech [[$block getDataBase] getTech]
    set dbu [$block getDbUnitsPerMicron]
    set clearance [expr { int($clearance_um * $dbu) }]
    set area [$block getDieArea]
    set die [list [$area xMin] [$area yMin] [$area xMax] [$area yMax]]
    lassign $die dx1 dy1 dx2 dy2
    set core [$block getCoreArea]

    set net [$block findNet $net_name]
    if { $net eq "NULL" } {
        error "pin template power net $net_name is not in the design; add it to VDD_NETS/GND_NETS"
    }

    # Edge coordinates: the port spans u1..u2 along its edge; the core starts
    # `margin` inward. Stripes that run toward this edge are on stripe_layer.
    if { $px1 < $dx1 || $px2 > $dx2 } {
        set u1 [expr { max($py1, $dy1) }]
        set u2 [expr { min($py2, $dy2) }]
        set stripe_layer $::env(PDN_HORIZONTAL_LAYER)
        if { $px1 < $dx1 } {
            set side W
            set margin [expr { [$core xMin] - $dx1 }]
        } else {
            set side E
            set margin [expr { $dx2 - [$core xMax] }]
        }
    } elseif { $py1 < $dy1 || $py2 > $dy2 } {
        set u1 [expr { max($px1, $dx1) }]
        set u2 [expr { min($px2, $dx2) }]
        set stripe_layer $::env(PDN_VERTICAL_LAYER)
        if { $py1 < $dy1 } {
            set side S
            set margin [expr { [$core yMin] - $dy1 }]
        } else {
            set side N
            set margin [expr { $dy2 - [$core yMax] }]
        }
    } else {
        error "power port of $net_name at ($px1 $py1) ($px2 $py2) is not on the die edge"
    }
    set where "the $side-edge power port of $net_name at ($px1 $py1) ($px2 $py2)"

    set bar_level [expr { [[$tech findLayer $stripe_layer] getRoutingLevel] - 1 }]
    set bar_layer [[$tech findRoutingLayer $bar_level] getName]
    set port_level [[$tech findLayer $port_layer] getRoutingLevel]
    if { $port_level != $bar_level && $port_level != $bar_level - 1 } {
        error "$where is on $port_layer, which cannot reach $stripe_layer stripes"
    }

    set v1 [expr { int($bar_start_um * $dbu) }]
    set v2 [expr { $margin - int($bar_end_gap_um * $dbu) }]
    if { $v2 - $v1 < 5 * $dbu } {
        error "the core margin on the $side edge ([expr { $margin / double($dbu) }] um) is too\
            small to connect the pad power ports; keep CORE_AREA as shipped"
    }

    # Stripes of this net that end at the core edge on this side, nearest
    # first: {distance u1 u2 end}, where `end` is how far from the die edge
    # the stripe stops.
    set center [expr { ($u1 + $u2) / 2 }]
    set stripes [list]
    foreach shape $shapes {
        lassign $shape shape_net layer sx1 sy1 sx2 sy2
        if { $shape_net ne $net_name || $layer ne $stripe_layer } {
            continue
        }
        switch $side {
            W { lassign [list $sy1 $sy2 [expr { $sx1 - $dx1 }] [expr { $sx2 - $sx1 }]] su1 su2 end length }
            E { lassign [list $sy1 $sy2 [expr { $dx2 - $sx2 }] [expr { $sx2 - $sx1 }]] su1 su2 end length }
            S { lassign [list $sx1 $sx2 [expr { $sy1 - $dy1 }] [expr { $sy2 - $sy1 }]] su1 su2 end length }
            N { lassign [list $sx1 $sx2 [expr { $dy2 - $sy2 }] [expr { $sy2 - $sy1 }]] su1 su2 end length }
        }
        if { $length <= $su2 - $su1 || $end > $margin + 10 * $dbu } {
            continue
        }
        lappend stripes [list [expr { abs(($su1 + $su2) / 2 - $center) }] $su1 $su2 $end]
    }
    if { [llength $stripes] == 0 } {
        error "net $net_name has no $stripe_layer stripes reaching the $side core edge\
            to connect its pad ports to"
    }
    set stripes [lsort -integer -index 0 $stripes]

    set metal [list \
        [list $port_layer {*}[place $side $die $u1 0 $u2 $v2] $clearance] \
        [list $bar_layer {*}[place $side $die $u1 $v1 $u2 $v2] $clearance]]
    if { [blocked $net_name $metal] } {
        error "no room in the $side core margin for $where; keep macros and core\
            rings out of the margin"
    }
    $net setSpecial
    set swire [odb::dbSWire_create $net ROUTED]
    draw $block $net_name $swire $metal
    if { $port_layer ne $bar_layer } {
        add_via $block $swire $port_layer $bar_layer {*}[place $side $die $u1 $v1 $u2 $v2]
    }

    return [dict create net $net_name where $where side $side die $die swire $swire \
        u1 $u1 u2 $u2 v1 $v1 v2 $v2 bar_layer $bar_layer stripe_layer $stripe_layer \
        stripes $stripes clearance $clearance dbu $dbu]
}

# Extend the bar of a started port to its nearest stripe that is still within
# reach, and connect the two. Returns the port with that stripe removed, or an
# empty string when no stripe can be reached.
proc dw_pads::extend_port { block port } {
    dict with port {
        set index -1
        foreach stripe $stripes {
            incr index
            lassign $stripe distance su1 su2 end
            # A stub continues its own stripe, so it only needs the spacing
            # the grid already keeps between stripes.
            set stub_end [expr { $end > $v2 ? $end + $dbu : $v2 }]
            set metal [list \
                [list $bar_layer {*}[place $side $die \
                    [expr { min($u1, $su1) }] $v1 [expr { max($u2, $su2) }] $v2] $clearance] \
                [list $stripe_layer {*}[place $side $die $su1 $v1 $su2 $stub_end] 0]]
            if { [blocked $net $metal] } {
                continue
            }
            draw $block $net $swire $metal
            add_via $block $swire $bar_layer $stripe_layer {*}[place $side $die $su1 $v1 $su2 $v2]
            dict set port stripes [lreplace $stripes $index $index]
            return $port
        }
    }
    return ""
}

proc dw_pads::connect_ports {} {
    variable stripes_per_port
    variable placed
    variable via_cache
    variable via_sites
    array unset via_cache
    array unset via_sites

    set block [ord::get_db_block]
    set dbu [$block getDbUnitsPerMicron]

    if { [info exists ::env(FP_DEF_TEMPLATE)] } {
        set template $::env(FP_DEF_TEMPLATE)
    } else {
        set template [file join [file dirname $::env(PDN_CFG)] pin_template.def]
    }

    set shapes [special_shapes $block]
    set placed $shapes
    foreach inst [$block getInsts] {
        if { [[$inst getMaster] isBlock] } {
            set box [$inst getBBox]
            lappend placed [list "" "*" [$box xMin] [$box yMin] [$box xMax] [$box yMax]]
        }
    }

    set ports [read_template_ports $template $dbu]
    if { [llength $ports] == 0 } {
        error "$template has no power ports"
    }
    # Claim every port's own strap first, so no bar is run across another
    # port. Then give every port one stripe before any port gets a second.
    set started [list]
    foreach port $ports {
        lappend started [start_port $block $port $shapes]
    }
    set reached 0
    for { set round 1 } { $round <= $stripes_per_port } { incr round } {
        set extended [list]
        foreach port $started {
            set next [extend_port $block $port]
            if { $next ne "" } {
                incr reached
                lappend extended $next
            } elseif { $round == 1 } {
                error "no room in the core margin to connect [dict get $port where] to\
                    its [dict get $port stripe_layer] stripes; keep macros and core rings\
                    out of the margin"
            }
        }
        set started $extended
    }
    puts "\[INFO\] Connected [llength $ports] pad power ports of [file tail $template]\
        to the power grid ($reached stripe connections)."
}

# GeneratePDN sources this file, then calls pdngen. The pad connections need
# the finished grid, so they are added right after pdngen returns.
if { [info commands dw_pads::pdngen_stock] eq "" } {
    rename pdngen dw_pads::pdngen_stock
    proc pdngen { args } {
        dw_pads::pdngen_stock {*}$args
        if { [lsearch -exact $args -reset] < 0 && [lsearch -exact $args -report_only] < 0 } {
            dw_pads::connect_ports
        }
    }
}
