Single-cell calibration of the SPICE-vs-Liberty delay gap (tt 25C 3.3V, CI ramp 0.375 ns 0-100 %
= 0.30 ns Liberty slew, A=1 B=0 so CI->CO is sensitized, 10 fF on CO and S).
  cal_sch.cir : PDK cell SPICE (libs.ref/.../spice, no parasitics)     -> addf_1_pdk_schematic.spice
  cal_pex.cir : Magic extraction of the PDK addf_1 GDS alone (same pex options as the block,
                C + coupling, no R; impl/scripts/magic_extract.sh settings) -> addf_1_magic_pex.spice
  c.tcl/c.log : OpenSTA on the PDK tt Liberty at the same boundary (0.30 ns, 10 fF)
Results (CI->CO, ns):          rise    fall
  SPICE, schematic (no C)      0.451   0.519
  Liberty (PDK, tt)            0.701   0.831
  SPICE, Magic PEX of cell     0.808   0.985
  PEX / Liberty                1.15    1.19
The block-level gap (SPICE-PEX / STA-SPEF sensitized = 1.13-1.22, all corners) is the same ratio, so it
comes from inside the cell (Magic's intra-cell C extraction vs the parasitics the PDK used to build
the Liberty), not from the routing (SPEF vs Liberty-only adds only 2-4 %).
Reproduce: ngspice -b cal_sch.cir ; ngspice -b cal_pex.cir (cwd = this dir); the PEX cell was made by
magic -dnull -noconsole -rcfile $PDK/libs.tech/magic/gf180mcuD.magicrc pex.tcl in a space-free dir
(/Users/samuelzhang/ttharden/ra_impl_pex_cell, LibreLane 3.0.14 container), subckt renamed addf_pex.
