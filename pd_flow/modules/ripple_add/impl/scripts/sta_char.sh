#!/bin/bash
# OpenSTA (LibreLane 3.0.14 container) characterisation of the hardened block, per corner:
#   1. SPEF-annotated STA (OpenRCX SPEF from the flow, nom RC) at the SPICE boundary
#      (input transition 0.30 ns Liberty convention, 20 fF on every output), arcs cin/a[0]/b[0] -> s[N-1];
#   2. the same without SPEF (Liberty cell delays only, no wire RC) for contrast;
#   3. write_timing_model from the SPEF-annotated design -> block Liberty view per corner;
#   4. the block Liberty read back on a wrapper and timed at the same boundary (view consistency);
#   5. vectorless power at input activity 0.5 per 100 ns (estimate only), max-slew check at 20 fF.
# Usage: sta_char.sh N
set -euo pipefail
N=$1; M=$((N-1))
HERE="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$HERE/n$N/sta"
source /Users/samuelzhang/ttsetup/env.sh
IMG=ghcr.io/librelane/librelane:3.0.14
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
LIBD=$PDKV/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib
W=/Users/samuelzhang/ttharden/ra_impl_sta_n$N
rm -rf "$W"; mkdir -p "$W"
cp "$HERE/n$N/run/final/nl/ripple_add.nl.v" "$W/"
cp "$HERE/n$N/run/final/spef/nom/ripple_add.nom.spef" "$W/" 2>/dev/null || cp "$HERE"/n$N/run/final/spef/nom/*.spef "$W/ripple_add.nom.spef"
cat > "$W/wrap.v" <<V
module wrap (input [$M:0] a, input [$M:0] b, input cin, output [$M:0] s);
  ripple_add u (.a(a), .b(b), .cin(cin), .s(s));
endmodule
V
ARCS="cin a[0] b[0]"
python3 - "$N" "$W/sens.tcl" <<'PY'
import sys
n, out = int(sys.argv[1]), sys.argv[2]
mask = (1 << n) - 1
scen = [("cin", mask, 0, None), ("a[0]", mask & ~1, 0, 1), ("b[0]", mask & ~1, 0, 1)]   # = spice_char.py
L = []
for drv, a, b, c in scen:
    fixed = []
    for i in range(n):
        for k, v in (("a", a), ("b", b)):
            p = f"{k}[{i}]"
            if p != drv:
                fixed.append((p, (v >> i) & 1))
    if drv != "cin":
        fixed.append(("cin", c))
    for p, v in fixed:
        L.append(f"set_case_analysis {v} [get_ports {{{p}}}]")
    for e in ("rise", "fall"):
        L.append(f'puts "ARC {drv} {e}"')
        L.append(f"report_checks -unconstrained -{e}_from [get_ports {{{drv}}}] -to [get_ports {{s[{n-1}]}}] "
                 "-format full -fields {slew cap} -digits 4")
    for p, v in fixed:
        L.append(f"unset_case_analysis [get_ports {{{p}}}]")
open(out, "w").write("\n".join(L) + "\n")
PY
for C in tt_025C_3v30 ss_125C_3v00 ff_n40C_3v60; do
cat > "$W/sta_$C.tcl" <<TCL
read_liberty $LIBD/gf180mcu_fd_sc_mcu7t5v0__$C.lib
read_verilog $W/ripple_add.nl.v
link_design ripple_add
proc boundary {} {
  set_input_transition 0.30 [all_inputs]
  set_load 0.020 [all_outputs]
}
boundary
puts "=== LIBERTY_ONLY (no wire parasitics)"
foreach f {$ARCS} { foreach e {rise fall} {
  puts "ARC \$f \$e"
  report_checks -unconstrained -\${e}_from [get_ports \$f] -to [get_ports {s[$M]}] -format full -fields {slew cap} -digits 4
}}
read_spef $W/ripple_add.nom.spef
puts "=== SPEF (OpenRCX nom)"
foreach f {$ARCS} { foreach e {rise fall} {
  puts "ARC \$f \$e"
  report_checks -unconstrained -\${e}_from [get_ports \$f] -to [get_ports {s[$M]}] -format full -fields {slew cap input_pins} -digits 4
}}
puts "=== SENSITIZED (SPEF; side inputs held by set_case_analysis as in the SPICE delay scenarios)"
source $W/sens.tcl
puts "=== MAX_SLEW_CHECK at 20 fF"
report_check_types -max_slew -max_capacitance -violators
report_check_types -max_slew -max_capacitance -verbose
puts "=== POWER (vectorless, input activity 0.5 per 100 ns, estimate)"
create_clock -name vclk -period 100
set_power_activity -input -activity 0.5
report_power -digits 6
write_timing_model -library_name ripple_add_$C -cell_name ripple_add $W/ripple_add__$C.lib
TCL
cat > "$W/model_$C.tcl" <<TCL
read_liberty $LIBD/gf180mcu_fd_sc_mcu7t5v0__$C.lib
read_liberty $W/ripple_add__$C.lib
read_verilog $W/wrap.v
link_design wrap
set_input_transition 0.30 [all_inputs]
set_load 0.020 [all_outputs]
puts "=== BLOCK_LIBERTY_MODEL"
foreach f {$ARCS} { foreach e {rise fall} {
  puts "ARC \$f \$e"
  report_checks -unconstrained -\${e}_from [get_ports \$f] -to [get_ports {s[$M]}] -format full -fields {slew cap} -digits 4
}}
TCL
done
docker run --rm -v "$PDKV:$PDKV" -v "$W:$W" -w "$W" $IMG bash -lc '
for C in tt_025C_3v30 ss_125C_3v00 ff_n40C_3v60; do
  sta -no_init -exit sta_$C.tcl > sta_$C.log 2>&1 || echo "sta $C rc=$?"
  sta -no_init -exit model_$C.tcl > model_$C.log 2>&1 || echo "model $C rc=$?"
done'
mkdir -p "$OUT"; cp "$W"/*.tcl "$W"/*.log "$W"/*.lib "$W/wrap.v" "$OUT/"
python3 "$HERE/scripts/sta_parse.py" "$OUT" "$N"
