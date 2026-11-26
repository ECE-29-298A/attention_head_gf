gds readonly true
gds read ripple_add.gds
load ripple_add
select top cell
extract path ./ext
extract do capacitance
extract do coupling
extract do adjust
extract no resistance
extract warn all
extract all
feedback save ext/extract_feedback.txt
ext2spice format ngspice
ext2spice scale off
ext2spice cthresh 0
ext2spice rthresh 0
ext2spice hierarchy off
ext2spice subcircuit top on
ext2spice global off
ext2spice -p ./ext -o ripple_add_pex.spice
puts "PEX_DONE"
quit -noprompt
