read_liberty /Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
read_verilog /Users/samuelzhang/ttharden/attention_head_gf/runs/wokwi/final/pnl/tt_um_attention_head_gf.pnl.v
link_design tt_um_attention_head_gf
read_sdc /Users/samuelzhang/ttharden/attention_head_gf/runs/wokwi/final/sdc/tt_um_attention_head_gf.sdc
read_spef /Users/samuelzhang/ttharden/attention_head_gf/runs/wokwi/final/spef/nom/tt_um_attention_head_gf.nom.spef
set f [open base_maxreg_cells.txt]; set names [split [string trim [read $f]] "\n"]; close $f
set cs {}
foreach n $names { lappend cs [get_cells $n] }
report_power
report_power -instances $cs > base_inst_power.rpt
