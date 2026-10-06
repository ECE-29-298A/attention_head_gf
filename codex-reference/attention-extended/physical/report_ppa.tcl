set ROOT [pwd]
set OUT $ROOT/report_ppa
file mkdir $OUT
set c $::env(PVT_CORNER)
set_thread_count 4
read_db $ROOT/run6/routed.odb
read_liberty $ROOT/platform/lib/sky130_fd_sc_hd__$c.lib
read_sdc $ROOT/run6/constraints.sdc
source $ROOT/platform/setRC.tcl
read_spef $ROOT/run6/extracted.spef
report_units
report_clock_min_period -include_port_paths
foreach period {100 33.333333 25 23 22.5 22.2 22.19 22.18 22 20 16.666667 14.1 14.07 14.06 13.34 13.3 13.29 13.28 12.5} {
  create_clock -name clk -period $period [get_ports clk]
  set_propagated_clock [all_clocks]
  set_clock_uncertainty 0.5 [get_clocks clk]
  set_clock_transition 1 [get_clocks clk]
  puts "PERIOD_NS $period"
  report_worst_slack -max
  report_worst_slack -min
  report_tns
}
create_clock -name clk -period 100 [get_ports clk]
set_propagated_clock [all_clocks]
set_clock_uncertainty 0.5 [get_clocks clk]
set_clock_transition 1 [get_clocks clk]
report_checks -path_delay min_max -fields {slew cap input nets fanout} -digits 6 > $OUT/timing_$c.rpt
report_check_types -max_slew -max_capacitance -violators > $OUT/electrical_$c.rpt
foreach activity {0.0 0.05 0.1 0.2} {
  set_power_activity -global -activity $activity -duty 0.5
  puts "POWER_ACTIVITY $activity AT_10MHZ CORNER $c"
  report_power -digits 6
}
exit
