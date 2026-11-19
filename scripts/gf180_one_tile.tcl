# Local GF180 place-and-route check using raw LEF and the Tiny Tapeout pin DEF.
set scl $::env(ATTENTION_SCL)
set cell gf180mcu_fd_sc_mcu7t5v0__
set top $::env(ATTENTION_TOP)
set_thread_count 6
define_corners tt ss ff
read_lef "$scl/tech/gf180mcu_5LM_1TM_11K_7t_tech.lef"
foreach lib_lef [lsort [glob -directory "$scl/cells" */*.lef]] {
    read_lef $lib_lef
}
read_liberty -corner tt tt.lib
read_liberty -corner ss ss.lib
read_liberty -corner ff ff.lib
read_verilog mapped.v
link_design $top
initialize_floorplan -die_area {0 0 346.64 160.72} -core_area {3.36 3.92 343.28 156.80} -site GF018hv5v_mcu_sc7
read_def -floorplan_initialize $::env(ATTENTION_TILE_DEF)
foreach layer {Metal1 Metal2 Metal3 Metal4} {
    make_tracks $layer -x_offset 0.28 -x_pitch 0.56 -y_offset 0.28 -y_pitch 0.56
}
make_tracks Metal5 -x_offset 0.45 -x_pitch 0.90 -y_offset 0.45 -y_pitch 0.90

create_clock -name clk -period $::env(ATTENTION_CLOCK_PERIOD) [get_ports clk]
set_input_delay -clock clk -max 4 [get_ports {ui_in* uio_in* ena rst_n}]
set_input_delay -clock clk -min 0 [get_ports {ui_in* uio_in* ena rst_n}]
set_output_delay -clock clk -max 4 [all_outputs]
set_output_delay -clock clk -min 0 [all_outputs]
set_clock_uncertainty 0.25 [get_clocks clk]
set_wire_rc -signal -layer Metal3
set_wire_rc -clock -layer Metal3
set_routing_layers -signal Metal2-Metal4 -clock Metal2-Metal4

add_global_connection -net VDD -inst_pattern .* -pin_pattern ^VDD$ -power
add_global_connection -net VSS -inst_pattern .* -pin_pattern ^VSS$ -ground
global_connect
tapcell -tapcell_master ${cell}filltie -distance 20
repair_tie_fanout -separation 0 ${cell}tieh/Z
repair_tie_fanout -separation 0 ${cell}tiel/ZN
global_connect
set_voltage_domain -power VDD -ground VSS
define_pdn_grid -name grid
add_pdn_stripe -grid grid -layer Metal1 -width 0.6 -followpins
add_pdn_stripe -grid grid -layer Metal4 -width 1.6 -spacing 1.7 -pitch 38.87 -offset 16.32
add_pdn_connect -grid grid -layers {Metal1 Metal4}
pdngen

global_placement -density $::env(ATTENTION_PLACEMENT_DENSITY)
detailed_placement
check_placement -verbose
report_design_area
write_def placed.def
clock_tree_synthesis -buf_list [list ${cell}clkbuf_2 ${cell}clkbuf_4 ${cell}clkbuf_8] -root_buf ${cell}clkbuf_4 -sink_clustering_enable
detailed_placement
set_propagated_clock [get_clocks clk]
estimate_parasitics -placement
repair_timing -hold -hold_margin 0.05 -max_buffer_percent 20 -allow_setup_violations
detailed_placement
global_connect
global_route -guide_file route.guide -congestion_iterations 60
estimate_parasitics -global_routing
report_worst_slack -max
report_worst_slack -min
set setup [sta::worst_slack -max]
set hold [sta::worst_slack -min]
if {$setup < 0 || $hold < 0} { error "Estimated setup or hold timing failed" }
detailed_route -output_drc drc.rpt -top_routing_layer Metal4 -droute_end_iter 40 -verbose 1
check_placement -verbose
report_design_area
if {[file size drc.rpt] != 0} { error "Detailed routing violations remain" }
check_antennas -report_file antenna.rpt
if {[file size antenna.rpt] != 0} { error "Antenna violations remain" }
set block [ord::get_db_block]
set unrouted 0
foreach net [$block getNets] {
    if {[$net isSpecial] || [$net getSigType] in {POWER GROUND}} { continue }
    set terminals [expr {[llength [$net getITerms]] + [llength [$net getBTerms]]}]
    if {$terminals > 1 && [$net getWire] eq "NULL"} {
        puts "Unrouted signal: [$net getName]"
        incr unrouted
    }
}
puts "Unrouted multi-terminal signals: $unrouted"
if {$unrouted != 0} { error "Unrouted signals remain" }
check_power_grid -net VDD -floorplanning
check_power_grid -net VSS -floorplanning
write_def routed.def
write_db routed.odb
write_verilog -sort -remove_cells [list ${cell}filltie] routed.v
