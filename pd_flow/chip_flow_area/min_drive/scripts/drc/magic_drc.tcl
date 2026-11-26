# Magic DRC of a GDS exactly as the TT precheck (tt/precheck/magic_drc.tcl) and LibreLane Magic.DRC
# run it: full GDS read (no maglef blackboxing), drc euclidean on, drc style drc(full).
# env: GDS, TOPCELL, RPT
gds maskhints yes
gds read $::env(GDS)
set fout [open $::env(RPT) w]
set oscale [cif scale out]
magic::suspendall
load $::env(TOPCELL)
select top cell
expand
drc euclidean on
drc style drc(full)
drc check
set drc_result [drc listall why]
set count 0
foreach {errtype coordlist} $drc_result {
    puts $fout "== $errtype"
    foreach coord $coordlist {
        set c [format " %.3f %.3f %.3f %.3f" [expr {$oscale * [lindex $coord 0]}] [expr {$oscale * [lindex $coord 1]}] [expr {$oscale * [lindex $coord 2]}] [expr {$oscale * [lindex $coord 3]}]]
        puts $fout $c
        incr count
    }
}
puts $fout "COUNT $count"
close $fout
puts "MAGIC_DRC_COUNT $count"
quit -noprompt
