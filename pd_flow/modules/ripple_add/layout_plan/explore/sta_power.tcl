# OpenSTA: worst a/b/cin -> s arrival and vectorless power of a fixed-width ripple_add netlist.
# Same boundary as opt/sta.tcl (0.30 ns input slew, 0.02 pF output load, 100 ns virtual clock,
# zero I/O delay, no wire load). Power: every input activity 0.5 transitions per 100 ns cycle,
# duty 0.5, propagated by OpenSTA (zero-delay probabilistic: no glitches, no wire C).
read_liberty $env(LIB)
read_verilog $env(NET)
link_design ripple_add
create_clock -name vclk -period 100
set_input_delay 0 -clock vclk [all_inputs]
set_output_delay 0 -clock vclk [all_outputs]
set_input_transition 0.30 [all_inputs]
set_load 0.02 [all_outputs]
report_checks -path_delay max -group_path_count 1 -fields {slew cap} -digits 3
set p [lindex [find_timing_paths -path_delay max] 0]
puts "RESULT $env(TAG) worst_arrival_ns=[format %.3f [expr 100.0 - [get_property $p slack]]] startpoint=[get_full_name [get_property $p startpoint]] endpoint=[get_full_name [get_property $p endpoint]]"
set q [lindex [find_timing_paths -from [get_ports cin] -path_delay max] 0]
puts "RESULT_CIN $env(TAG) cin_arrival_ns=[format %.3f [expr 100.0 - [get_property $q slack]]]"
set_power_activity -input -activity 0.5 -duty 0.5
report_power -digits 6
