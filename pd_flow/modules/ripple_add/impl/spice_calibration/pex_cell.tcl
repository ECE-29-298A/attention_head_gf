gds readonly true
gds read lib.gds
load gf180mcu_fd_sc_mcu7t5v0__addf_1
select top cell
extract path ./ext
extract do capacitance
extract do coupling
extract do adjust
extract no resistance
extract all
ext2spice format ngspice
ext2spice scale off
ext2spice cthresh 0
ext2spice hierarchy off
ext2spice subcircuit top on
ext2spice -p ./ext -o addf_1_pex.spice
quit -noprompt
