read_liberty /Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__ff_n40C_3v60.lib
read_verilog /Users/samuelzhang/ttharden/ra_impl_sta_n12/ripple_add.nl.v
link_design ripple_add
proc boundary {} {
  set_input_transition 0.30 [all_inputs]
  set_load 0.020 [all_outputs]
}
boundary
puts "=== LIBERTY_ONLY (no wire parasitics)"
foreach f {cin a[0] b[0]} { foreach e {rise fall} {
  puts "ARC $f $e"
  report_checks -unconstrained -${e}_from [get_ports $f] -to [get_ports {s[11]}] -format full -fields {slew cap} -digits 4
}}
read_spef /Users/samuelzhang/ttharden/ra_impl_sta_n12/ripple_add.nom.spef
puts "=== SPEF (OpenRCX nom)"
foreach f {cin a[0] b[0]} { foreach e {rise fall} {
  puts "ARC $f $e"
  report_checks -unconstrained -${e}_from [get_ports $f] -to [get_ports {s[11]}] -format full -fields {slew cap input_pins} -digits 4
}}
puts "=== SENSITIZED (SPEF; side inputs held by set_case_analysis as in the SPICE delay scenarios)"
source /Users/samuelzhang/ttharden/ra_impl_sta_n12/sens.tcl
puts "=== MAX_SLEW_CHECK at 20 fF"
report_check_types -max_slew -max_capacitance -violators
report_check_types -max_slew -max_capacitance -verbose
puts "=== POWER (vectorless, input activity 0.5 per 100 ns, estimate)"
create_clock -name vclk -period 100
set_power_activity -input -activity 0.5
report_power -digits 6
write_timing_model -library_name ripple_add_ff_n40C_3v60 -cell_name ripple_add /Users/samuelzhang/ttharden/ra_impl_sta_n12/ripple_add__ff_n40C_3v60.lib
