# OpenSTA: worst combinational path a/b/cin -> s of a mapped ripple_add netlist.
# Env: LIB (liberty), NET (netlist), TAG. Input slew 0.30 ns on every input, 0.02 pF on every
# output (about four drive-1 input pins); virtual 100 ns clock, zero I/O delays, no wire load.
# Arrival = period - slack (output delay 0, required time = 100 ns).
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
foreach st {cin a[0] b[0]} {
  set q [lindex [find_timing_paths -from [get_ports $st] -path_delay max] 0]
  puts "RESULT_FROM $env(TAG) from=$st arrival_ns=[format %.3f [expr 100.0 - [get_property $q slack]]] endpoint=[get_full_name [get_property $q endpoint]]"
}
