read_liberty /Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
read_verilog /Users/samuelzhang/ttharden/ra_impl_cal_sta/c.v
link_design c
set_input_transition 0.30 [all_inputs]
set_load 0.010 [all_outputs]
set_case_analysis 1 [get_ports A]
set_case_analysis 0 [get_ports B]
report_checks -unconstrained -rise_from [get_ports CI] -to [get_ports CO] -digits 4 -fields {slew}
report_checks -unconstrained -fall_from [get_ports CI] -to [get_ports CO] -digits 4 -fields {slew}
