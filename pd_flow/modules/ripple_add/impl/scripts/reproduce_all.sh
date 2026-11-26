#!/bin/bash
# Phase 4 (ripple_add) end-to-end reproduction, in the order the evidence was produced.
# Run from anywhere; every step writes under impl/. Docker steps run one at a time (one harden at a time).
# Prereqs: /Users/samuelzhang/ttsetup/env.sh (LibreLane 3.0.14 venv, PDK_ROOT), Docker with
# ghcr.io/librelane/librelane:3.0.14, host KLayout (/Applications/klayout.app), ngspice >= 47,
# /usr/local/bin/python3 with cocotb 2.0 + Icarus 13 (for the top test).
set -euo pipefail
IMPL="$(cd "$(dirname "$0")/.." && pwd)"
MOD="$(cd "$IMPL/.." && pwd)"
ROOT="$(cd "$MOD/../../.." && pwd)"
S="$IMPL/scripts"
PY=/usr/local/bin/python3
FA3="$MOD/layout_plan/chip_runs/fixed_a3/harden"
cd "$IMPL"

for N in 22 12; do
  "$S/run_block.sh" $N                                        # 1. LibreLane harden (FIXED placement, auto route)
  $PY "$S/check_block.py" $N n$N/run n$N/check_block.json     #    placement/pins/netlist/routing/size checks
  for G in n$N/run/final/gds/ripple_add.gds; do               # 2. full KLayout GF180 deck (main/antenna/density)
    "$S/run_klayout_drc.sh" "$G" ripple_add n$N/drc n$N
  done
  $PY "$S/make_cdl.py" n$N/run/final/pnl/ripple_add.pnl.v n$N/lvs/ripple_add_n$N.cdl cdl --sub VSUB --omit-empty
  $PY "$S/make_cdl.py" n$N/run/final/pnl/ripple_add.pnl.v n$N/lvs/ripple_add_n$N.spice spice
  RUN_MODE=deep "$S/run_klayout_lvs.sh" n$N/run/final/gds/ripple_add.gds n$N/lvs/ripple_add_n$N.cdl n$N/lvs klvs_n$N
  "$S/magic_extract.sh" $N                                    # 5. Magic transistor-level PEX (C + coupling)
  "$S/sta_char.sh" $N                                         # 6/7. OpenSTA+SPEF characterisation, block Liberty
  $PY "$S/extracted_to_verilog.py" n$N/run/final/spice/ripple_add.spice $N contract/ripple_add_n${N}_extracted.v
  "$MOD/verif/run_all.sh" --rtl contract/ripple_add_n${N}_extracted.v --gate $N --out contract/n${N}_extracted --jobs 3
  "$MOD/verif/run_all.sh" --rtl views/ripple_add_n${N}_behav.v --gate $N --out contract/n${N}_behav --jobs 3
done
# 3b. Netgen LVS controls (positive control + swapped-output negative control) for N=22
"$S/netgen_lvs.sh" n22/run/final/spice/ripple_add.spice n22/run/final/pnl/ripple_add.pnl.v n22/lvs/negative_control netgen_pos
# 6. ngspice post-layout characterisation (N=22 all corners, N=12 tt)
for C in tt ss ff; do $PY "$S/spice_char.py" 22 $C n22/spice; done
$PY "$S/spice_char.py" 22 tt n22/spice_schematic delay --netlist n22/lvs/ripple_add_n22.spice
$PY "$S/spice_char.py" 12 tt n12/spice func delay
(cd spice_calibration && ngspice -b cal_sch.cir && ngspice -b cal_pex.cir)
# 7. view manifest + consistency
for N in 22 12; do $PY "$S/check_views.py" $N views/views_n$N.json; done
# 8. integration evidence on layout_plan/chip_runs/fixed_a3 (not shipped)
$PY "$S/check_chip_integration.py" integration/chip_netlist_check.json
"$S/run_klayout_drc.sh" /Users/samuelzhang/ttharden/ra_fixed_a3/runs/wokwi/final/gds/tt_um_attention_head_gf.gds \
    tt_um_attention_head_gf chip_context/drc_fixed_a3 fixed_a3
(cd integration && $PY ../scripts/make_gl_models.py cell_models_init0_pwr.v zero --power-pins \
               && $PY ../scripts/make_gl_models.py cell_models_initrand_pwr.v random --power-pins \
               && $PY ../scripts/make_gl_models.py cell_models_init0_nopwr.v zero)
cd "$ROOT"
I=pd_flow/modules/ripple_add/impl/integration
$PY test/top/run.py --netlist "$FA3/pnl/tt_um_attention_head_gf.pnl.v" --cell-models "$I/cell_models_init0_pwr.v"
$PY test/top/run.py --netlist "$FA3/pnl/tt_um_attention_head_gf.pnl.v" --cell-models "$I/cell_models_initrand_pwr.v"
$PY test/top/run.py --netlist "$FA3/nl/tt_um_attention_head_gf.nl.v"   --cell-models "$I/cell_models_init0_nopwr.v"
# negative control: must FAIL
! $PY test/top/run.py --netlist "$I/negative_control/tt_um_swap_s3_s4.nl.v" --cell-models "$I/cell_models_init0_nopwr.v"
