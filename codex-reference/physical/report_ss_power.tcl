set ROOT [pwd]
set_thread_count 2
read_db $ROOT/run6/routed.odb
read_liberty $ROOT/platform/lib/sky130_fd_sc_hd__ss_100C_1v60.lib
read_sdc $ROOT/run6/constraints.sdc
source $ROOT/platform/setRC.tcl
read_spef $ROOT/run6/extracted.spef
set_power_activity -global -activity 0.2 -duty 0.5
report_power -digits 6
exit
