read_liberty /Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
read_verilog /Users/samuelzhang/ttharden/mr3_a_sdff/runs/wokwi/final/pnl/tt_um_attention_head_gf.pnl.v
link_design tt_um_attention_head_gf
read_sdc /Users/samuelzhang/ttharden/mr3_a_sdff/runs/wokwi/final/sdc/tt_um_attention_head_gf.sdc
read_spef /Users/samuelzhang/ttharden/mr3_a_sdff/runs/wokwi/final/spef/nom/tt_um_attention_head_gf.nom.spef
set blk [get_cells -hierarchical {core.max_unit.*}]
puts "block cells: [llength $blk]"
report_power
report_power -instances $blk > blk_inst_power.rpt
report_power -instances [get_cells {fanout1 max_cap5}]
foreach n {core.max_unit.nld_b net1} { report_net -connections $n }
