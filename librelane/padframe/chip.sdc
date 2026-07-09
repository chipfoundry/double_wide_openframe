# Double-wide openframe is a passive pass-through pad ring: there is no internal
# clock or logic. This SDC only sets conservative IO defaults so the STA steps
# have something to chew on.

set_units -time ns -capacitance pF

# Treat all bond-pad inputs as loosely constrained.
set all_in [all_inputs]
if { [llength $all_in] > 0 } {
    set_input_delay 0 $all_in
}
set all_out [all_outputs]
if { [llength $all_out] > 0 } {
    set_output_delay 0 $all_out
}
