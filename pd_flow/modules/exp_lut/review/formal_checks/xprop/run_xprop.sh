#!/bin/bash
# Agent 2: formal X-propagation check (D9) proposed for the contract. Yosys SAT with undef
# modelling: with every input defined (and, for REGISTERED = 1, a defined initial state, as in
# silicon), can any bit of W (or done) be X? "no model found" = X-free for every input (r0) /
# every defined state and input (r1, one step; X-freedom of a register is 1-inductive).
# Usage: run_xprop.sh <rtl.v> <REGISTERED>   prints "xprop ok" or "xprop X-reachable"
set -u
export PATH="/opt/homebrew/bin:$PATH"
T="$(mktemp -d "${TMPDIR:-/tmp}/el_xp.XXXXXX")"; cp "$1" "$T/dut.v"; R=$2; res=ok
for sig in W done; do
  if [ "$R" = 0 ]; then S="-set-any-undef $sig"; else S="-seq 2 -set-init-def -set-any-undef-at 2 $sig"; fi
  ( cd "$T" && yosys -q -l x.log -p "read_verilog -sv dut.v; chparam -set REGISTERED $R exp_lut; hierarchy -top exp_lut; proc -norom; flatten; opt_clean; sat -enable_undef -set-def-inputs $S exp_lut" ) >/dev/null 2>&1
  grep -q "SAT solving finished - no model found" "$T/x.log" || res="X-reachable($sig)"
done
echo "xprop R=$R $res"; rm -rf "$T"; [ "$res" = ok ]
