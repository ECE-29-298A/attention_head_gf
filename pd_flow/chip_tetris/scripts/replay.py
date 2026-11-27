#!/usr/bin/env python3
"""Replay the whole-chip tetris recipe on any reference run (netlist-agnostic, one command).

Everything is re-derived from the reference run (its synthesized netlist, final and step-34 DEFs, area classes,
SPEF); no instance name is carried over from another netlist.  Steps:
  0. baselines: baseline/<ref>_area_classes.json, _crit.json, _cts.json (area_classes.py, crit.py, cts_leaves.py)
  1. r32 reproduction check: the tool's step-34 placement handed off after step 32 must give the reference's area
  2. r32 screen of the tool's final placement (its flop set = the post-CTS-legalization sink positions)
  3. CTS sink-cluster search from that flop set (cts_search.py: flop relocations scored by the real CTS)
  4. chip-wide anneals of every non-flop cell (genw.sh recipe: repair + criticality weighted HPWL, flops frozen),
     annealer seeds 1..S and the D8c compaction sequence (pack-w 0/10/20/40), on the best flop set
  5. r32 dry runs through step 55 of every candidate; gate (compare.py); winner = lowest area, then lowest slew
  6. robustness: 2 low-temperature re-anneals of the winner with new seeds (flops frozen)
  7. --signoff: full harden of the winner in /Users/samuelzhang/ttharden/wc_<prefix>_win (run_signoff.sh, r32)
usage: replay.py <reference run dir (…/runs/wokwi)> <prefix> [--seeds 3] [--signoff]
Writes logs/replay_<prefix>.json."""
import sys, os, json, glob, subprocess, argparse
here = os.path.dirname(os.path.abspath(__file__)); root = os.path.dirname(here)
ap = argparse.ArgumentParser(); ap.add_argument('ref'); ap.add_argument('prefix'); ap.add_argument('--seeds', type=int, default=3)
ap.add_argument('--signoff', action='store_true'); a = ap.parse_args()
env = dict(os.environ, DP_REF=a.ref)
sys.path.insert(0, here); os.environ['DP_REF'] = a.ref
import dplib, compare  # noqa: E402  (imported with DP_REF set)
TAG = dplib.REF_TAG; P = a.prefix; WK = '/Users/samuelzhang/ttharden/wc_work'
out = {'reference': a.ref, 'ref_tag': TAG, 'prefix': P}


def sh(cmd, **kw):
    print('+', cmd if isinstance(cmd, str) else ' '.join(cmd), flush=True)
    return subprocess.run(cmd, shell=isinstance(cmd, str), cwd=root, env=dict(env, **kw.pop('env', {})), check=True,
                          capture_output=True, text=True, **kw).stdout


def summary(tag, mode='r32'):
    return json.load(open(f'{WK}/{tag}_{"r32" if mode == "r32" else "firm"}/summary.json'))


# 0 baselines
fin = glob.glob(a.ref + '/final/def/*.def')[0]; s34 = glob.glob(a.ref + '/34-*/*.def')[0]
sh(['python3', 'scripts/area_classes.py', fin, '--json', f'baseline/{TAG}_area_classes.json'])
sh(['python3', 'scripts/crit.py', '--json', f'baseline/{TAG}_crit.json'])
sh(['python3', 'scripts/cts_leaves.py', glob.glob(a.ref + '/35-*/*.def')[0], '--json', f'baseline/{TAG}_cts.json', '-q'])
# 1, 2
sh(['python3', 'scripts/gen_tetris.py', '--out', f'placements/{P}_s34', '--seed-def', s34])
sh(['python3', 'scripts/gen_tetris.py', '--out', f'placements/{P}_s0', '--seed-def', fin])
for t in (f'{P}_s34', f'{P}_s0'):
    sh(['python3', 'scripts/pipeline.py', f'placements/{t}', t, '--mode', 'r32'])
out['repro'] = compare.row(summary(f'{P}_s34')); out['s0'] = compare.row(summary(f'{P}_s0'))
# 3
sh(['python3', 'scripts/cts_search.py', f'{P}_g', '--rounds', '3', '--per-round', '8', '--base-args', f'--seed-def {fin}'])
cs = json.load(open(os.path.join(root, 'logs', f'cts_search_{P}_g.json')))['best']
reloc = ' '.join(cs['relocs']); out['cts_search'] = {'best': cs['tag'], 'cts_area': cs['cts_area'], 'relocs': cs['relocs']}
# 4, 5
cands = []
for rl, lab in ((reloc, 'g'), ('', 'n')) if reloc else (('', 'n'),):
    for s in range(1, a.seeds + 1):
        cands.append((f'{P}_{lab}a{s}', rl, ['--seed', str(s)]))
    for w in (10, 20, 40):
        cands.append((f'{P}_{lab}p{w}', rl, ['--seed', '1', '--pack-w', str(w)]))
for t, rl, extra in cands:
    sh(['scripts/genw.sh', t] + extra, env={'SEED': 'final', 'RELOC': rl})
sh(['scripts/run_batch.sh', 'r32'] + [t for t, _, _ in cands])
rows = [compare.row(summary(t)) for t, _, _ in cands]
out['screens'] = rows
ok = [r for r in rows if r['pass']]
if not ok:
    out['winner'] = None; json.dump(out, open(os.path.join(root, 'logs', f'replay_{P}.json'), 'w'), indent=1)
    sys.exit('no candidate passes the gate')
win = min(ok, key=lambda r: (r['area'], int(r['slew_cap_fo'].split('/')[0])))
out['winner'] = win
# 6 robustness: re-anneal the winner locally (flops frozen) with new seeds
wt = win['tag']
for k, s in (('p1', 11), ('p2', 12)):
    sh(['python3', 'scripts/gen_tetris.py', '--out', f'placements/{wt}_{k}', '--init', f'placements/{wt}', '--iters', '20000',
        '--T0', '0.05', '--seed', str(s), '--weights', 'repair', '--repair-from', f'baseline/{TAG}_area_classes.json', '--K', '4',
        '--K2', '30', '--crit', f'baseline/{TAG}_crit.json', '--freeze-flops'])
sh(['scripts/run_batch.sh', 'r32', f'{wt}_p1', f'{wt}_p2'])
out['robustness'] = [compare.row(summary(f'{wt}_{k}')) for k in ('p1', 'p2')]
json.dump(out, open(os.path.join(root, 'logs', f'replay_{P}.json'), 'w'), indent=1)
# 7
if a.signoff:
    sh(['scripts/run_signoff.sh', f'{P}_win', f'placements/{wt}', 'r32', os.path.dirname(os.path.dirname(a.ref))])
print('winner', win['tag'], win['area'], win['d_area'], win['slew_cap_fo'])
