# Set placement status on std cells of an ODB (LibreLane image OpenROAD).
# env: IN_ODB, OUT_ODB, STATUS (FIRM|PLACED), LIST (optional file: one instance name per line;
# default = every instance that is not a tap/endcap/fill), LOC (optional file "name x y orient"
# in microns: also move the instance there).
read_db $::env(IN_ODB)
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set want {}
if {[info exists ::env(LIST)] && $::env(LIST) ne ""} {
  set f [open $::env(LIST)]; foreach l [split [read $f] "\n"] { if {$l ne ""} { dict set want $l 1 } }; close $f
}
set loc {}
if {[info exists ::env(LOC)] && $::env(LOC) ne ""} {
  set f [open $::env(LOC)]
  foreach l [split [read $f] "\n"] { if {[llength $l] == 4} { dict set loc [lindex $l 0] [lrange $l 1 3] } }
  close $f
}
set n 0; set moved 0
foreach inst [$block getInsts] {
  set m [[$inst getMaster] getName]
  set nm [$inst getName]
  if {[string match "*filltie*" $m] || [string match "*endcap*" $m] || [string match "*__fill*" $m]} continue
  if {[dict size $want] > 0 && ![dict exists $want $nm]} continue
  if {[dict exists $loc $nm]} {
    lassign [dict get $loc $nm] x y o
    $inst setOrient [string map {N R0 FS MX FN MY S R180} $o]
    $inst setLocation [expr {round($x * $dbu)}] [expr {round($y * $dbu)}]
    incr moved
  }
  $inst setPlacementStatus $::env(STATUS)
  incr n
}
puts "SETSTATUS $::env(STATUS): $n instances, moved $moved"
write_db $::env(OUT_ODB)
