#!/bin/bash
# whole-chip candidate generator: [RELOC="c:x:y ..."] [ITERS=N] genw.sh <tag> [extra gen_tetris args...]
# recipe = seed: the reference run's step-34 (tool DPL, pre-CTS) placement, or SEED=final its final placement; RELOC: the CTS sink-cluster flop moves
# (from cts_search.py); then a chip-wide legal-move anneal of every non-flop cell on repair + criticality weighted
# HPWL (D10 §2: repaired/upsized drivers' nets x4, those with seed HPWL >= 60 um x30, crit weights); flops frozen
# so the CTS sink set (and with it the clock tree) is the RELOC one.  Reference = dplib.REF (default wc_ref2).
cd "$(dirname "$0")/.."
REFRUN=$(python3 -c "import sys; sys.path.insert(0, 'scripts'); import dplib; print(dplib.REF, end='')")
TAGREF=$(python3 -c "import sys; sys.path.insert(0, 'scripts'); import dplib; print(dplib.REF_TAG, end='')")
if [ "${SEED:-34}" = final ]; then S34=$(ls $REFRUN/final/def/*.def); else S34=$(ls $REFRUN/34-openroad-detailedplacement/*.def); fi
TAG=$1; shift
python3 scripts/gen_tetris.py --out placements/$TAG --seed-def $S34 ${RELOC:+--relocate $RELOC} \
  --iters ${ITERS:-300000} --weights repair --repair-from baseline/${TAGREF}_area_classes.json --K 4 --K2 30 --hpwl-thr 60 \
  --crit baseline/${TAGREF}_crit.json --freeze-flops "$@" > logs/gen_$TAG.log 2>&1
tail -1 logs/gen_$TAG.log
