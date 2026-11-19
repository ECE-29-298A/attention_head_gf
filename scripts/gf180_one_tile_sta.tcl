# Run each OpenRCX extraction in a fresh process, then load its SPEF in STA.
if {[info exists ::env(ATTENTION_RC_CORNER)]} {
    read_db routed.odb
    define_process_corner -ext_model_index 0 rc
    extract_parasitics -ext_model_file $::env(ATTENTION_RC_RULES)
    write_spef routed-$::env(ATTENTION_RC_CORNER).spef
} else {
    define_corners tt ss ff
    foreach corner {tt ss ff} { read_liberty -corner $corner $corner.lib }
    read_db routed.odb
    create_clock -name clk -period $::env(ATTENTION_CLOCK_PERIOD) [get_ports clk]
    set_input_delay -clock clk -max 4 [get_ports {ui_in* uio_in* ena rst_n}]
    set_input_delay -clock clk -min 0 [get_ports {ui_in* uio_in* ena rst_n}]
    set_output_delay -clock clk -max 4 [all_outputs]
    set_output_delay -clock clk -min 0 [all_outputs]
    set_clock_uncertainty 0.25 [get_clocks clk]
    set_input_transition 1 [all_inputs]
    set_load 0.01 [all_outputs]
    set_propagated_clock [get_clocks clk]
    read_spef -corner tt routed-nom.spef
    read_spef -corner ss routed-max.spef
    read_spef -corner ff routed-min.spef
    report_parasitic_annotation -report_unannotated
    report_worst_slack -max -digits 3
    report_worst_slack -min -digits 3
    report_checks -path_delay min_max -format full_clock_expanded
    report_check_types -max_slew -max_capacitance -max_fanout -violators
}
