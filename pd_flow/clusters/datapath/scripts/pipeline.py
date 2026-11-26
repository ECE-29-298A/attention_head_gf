#!/usr/bin/env python3
"""Reservation fixpoint + FIRM screening of one candidate placement.
usage: pipeline.py <placement_dir> <tag> [--rounds 4] [--through 55] [--skip-probe]
  1. probe (steps 17-32, PLACED before repair) -> cells the resizer upsizes for this placement;
  2. any upsize wider than its span is reserved in place (dplib.reserve: the span grows on the side
     the in-place swap grows, row neighbours shift, order kept) -> <placement_dir>_r<k>; re-probe
     until no miss (at most --rounds);
  3. FIRM dry run through step 55 on the converged placement.
Work dirs: /Users/samuelzhang/ttharden/dp_work/<tag>_probe<k>, <tag>_firm.
Prints one DRYRUN line; the FIRM summary is <work>/summary.json and is copied next to the placement."""
import sys, os, json, argparse, subprocess, shutil
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib

ap = argparse.ArgumentParser(); ap.add_argument('pdir'); ap.add_argument('tag')
ap.add_argument('--rounds', type=int, default=4); ap.add_argument('--through', default='55')
ap.add_argument('--skip-probe', action='store_true')
a = ap.parse_args()
WK = '/Users/samuelzhang/ttharden/dp_work'
pdir = a.pdir.rstrip('/')
def dry(p, work, probe, through):
    cmd = [sys.executable, os.path.join(here, 'dryrun.py'), p, work, '--through', through] + (['--probe'] if probe else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    line = [l for l in r.stdout.splitlines() if l.startswith('DRYRUN')]
    print(line[-1] if line else r.stdout[-1500:], flush=True)
    s = os.path.join(work, 'summary.json')
    return json.load(open(s)) if os.path.exists(s) else None
if not a.skip_probe:
    d = dplib.Design()
    for k in range(a.rounds):
        s = dry(pdir, f'{WK}/{a.tag}_probe{k}', True, '32')
        if s is None or not s['chain_ok']:
            print('PIPELINE probe failed'); sys.exit(1)
        json.dump(s['resized_at_32'], open(os.path.join(pdir, f'probe{k}_resized.json'), 'w'), indent=1)
        miss = s['reservation_misses']
        if not miss:
            break
        P = dplib.Placement.load(d, pdir)
        res = {n: m for n, m in s['resized_at_32'].items()}
        need = {n: m for n, m in res.items() if d.wsites(m) > P.cells[n]['wr']}
        moved = dplib.reserve(P, need)
        nd = f'{pdir}_r{k + 1}' if not pdir.endswith(f'_r{k}') else pdir[:-len(f'_r{k}')] + f'_r{k + 1}'
        P.write(nd, {'reserve_round': k + 1, 'from': pdir, 'reserved_now': need, 'shifted': moved,
                     'hpwl_pins_um': round(dplib.Wire(P).total(), 1)})
        print(f'PIPELINE round {k}: {len(need)} misses {need} -> {nd} (shifted {len(moved)})', flush=True)
        pdir = nd
    else:
        print('PIPELINE reservation did not converge'); sys.exit(1)
s = dry(pdir, f'{WK}/{a.tag}_firm', False, a.through)
if s:
    json.dump(s, open(os.path.join(pdir, 'firm_summary.json'), 'w'), indent=1)
print('PIPELINE final placement', pdir)
