read_liberty /Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
read_liberty /Users/samuelzhang/ttharden/ra_impl_sta_n22/ripple_add__tt_025C_3v30.lib
read_verilog /Users/samuelzhang/ttharden/ra_impl_sta_n22/wrap.v
link_design wrap
set_input_transition 0.30 [all_inputs]
set_load 0.020 [all_outputs]
puts "=== BLOCK_LIBERTY_MODEL"
foreach f {cin a[0] b[0]} { foreach e {rise fall} {
  puts "ARC $f $e"
  report_checks -unconstrained -${e}_from [get_ports $f] -to [get_ports {s[21]}] -format full -fields {slew cap} -digits 4
}}
