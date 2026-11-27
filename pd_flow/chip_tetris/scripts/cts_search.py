#!/usr/bin/env python3
"""Greedy CTS sink-cluster search with the real tool in the loop (r32 mode, steps 33' 34 35 of the reference).

The clock tree's leaf dummies (clkload*) pad every leaf whose clock-pin cap is below its subtree's largest leaf
(measured: wc_ref, wc_ref2).  Their area therefore depends only on how the flops are clustered, and the leaf count
is at its floor (ceil(sinks / CTS_SINK_CLUSTERING_SIZE)).  Each round proposes flop relocations that move a flop
of one partial leaf (fewer than SIZE sinks) into the bounding box of another partial leaf (concentrating the
leaves' deficit, which the dummy cells pad), screens them with the real CTS, and keeps the best if it lowers the
CTS area.  Candidates are plain gen_tetris.py argument lists (the relocations are recorded in gen.json).
usage: cts_search.py <tag> [--rounds 4] [--per-round 8] [--jobs 2] [--base-args '...']
Writes logs/cts_search_<tag>.json (every candidate, its relocations and CTS census) and placements/<tag>_best."""
import sys, os, json, glob, subprocess, argparse, shlex, concurrent.futures as cf
here = os.path.dirname(os.path.abspath(__file__)); root = os.path.dirname(here); sys.path.insert(0, here)
import dplib
sys.path.insert(0, os.path.join(dplib.BDIR, 'tools'))
from def_nets import read_nets
from pdlib import read_def
ap = argparse.ArgumentParser(); ap.add_argument('tag'); ap.add_argument('--rounds', type=int, default=4)
ap.add_argument('--per-round', type=int, default=8); ap.add_argument('--jobs', type=int, default=2)
ap.add_argument('--base-args', default=''); ap.add_argument('--size', type=int, default=20)
a = ap.parse_args()
S34 = glob.glob(os.path.join(glob.glob(os.path.join(dplib.REF, '34-*'))[0], '*.def'))[0]
base = ['--seed-def', S34] + shlex.split(a.base_args)
WK = '/Users/samuelzhang/ttharden/wc_work'


def screen(tag, relocs):
    pd = os.path.join(root, 'placements', tag)
    args = base + (['--relocate'] + relocs if relocs else [])
    r = subprocess.run([sys.executable, os.path.join(here, 'gen_tetris.py'), '--out', pd] + args, capture_output=True, text=True, cwd=root)
    open(os.path.join(root, 'logs', f'gen_{tag}.log'), 'w').write(r.stdout + r.stderr)
    if r.returncode: return {'tag': tag, 'relocs': relocs, 'error': (r.stdout + r.stderr)[-300:]}
    w = f'{WK}/{tag}_cts'
    subprocess.run([sys.executable, os.path.join(here, 'dryrun.py'), pd, w, '--mode', 'r32', '--through', '35'], capture_output=True, text=True)
    s = json.load(open(os.path.join(w, 'summary.json'))); c = s.get('cts') or {}
    return {'tag': tag, 'relocs': relocs, 'args': args, 'cts_area': c.get('cts_area'), 'dummies': c.get('dummies'),
            'leaves': c.get('n_leaves'), 'masters': c.get('masters'), 'fanouts': sorted(l['ff'] for l in c.get('leaves', [])),
            'held': s.get('ALL_HELD'), 'work': w}


def proposals(res, k):
    """flop moves from partial leaf A into partial leaf B's box (A smaller than B, B < size), nearest flops first."""
    f = glob.glob(os.path.join(res['work'], 'chain', '*-35-*', '*.def'))[0]
    N = read_nets(f); C = read_def(f)['comps']; leaves = {}
    for net, conns in N.items():
        drv = [i for i, p in conns if i.startswith('clkbuf_') and p == 'Z']
        if not drv: continue
        ff = [i for i, p in conns if i != drv[0] and not i.startswith(('clkload', 'clkbuf_')) and i != 'PIN']
        if ff: leaves[drv[0]] = ff
    xy = lambda i: (C[i]['x'], C[i]['y'])
    box = {L: (min(xy(i)[0] for i in ff), min(xy(i)[1] for i in ff), max(xy(i)[0] for i in ff), max(xy(i)[1] for i in ff)) for L, ff in leaves.items()}
    part = [L for L, ff in leaves.items() if len(ff) < a.size]
    out = []
    for A in part:
        for B in part:
            if A == B or len(leaves[A]) > len(leaves[B]): continue
            x0, y0, x1, y1 = box[B]
            for i in leaves[A]:
                x, y = xy(i)
                tx, ty = min(max(x, x0 + 4), x1 - 4), min(max(y, y0 + 2), y1 - 2)
                dist = abs(tx - x) + abs(ty - y)
                if dist < 2: continue
                out.append((dist, f'{i}:{tx:.1f}:{ty:.1f}', A, B))
    out.sort()
    seen, sel = set(), []
    for dist, mv, A, B in out:              # at most two proposals per (A, B) pair, nearest first
        key = (A, B)
        if sum(1 for q in sel if q[1] == key) >= 2: continue
        sel.append((mv, key, round(dist, 1)))
        if len(sel) >= k: break
    return sel


log = []
best = screen(f'{a.tag}_r0', [])
log.append(best); print('base', best.get('cts_area'), best.get('fanouts'), flush=True)
for rnd in range(1, a.rounds + 1):
    props = proposals(best, a.per_round)
    if not props: break
    cands = [(f'{a.tag}_r{rnd}_{j}', best['relocs'] + [mv]) for j, (mv, key, dist) in enumerate(props)]
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(lambda t: screen(*t), cands))
    for r_ in res:
        log.append(r_); print(rnd, r_['tag'], r_.get('cts_area'), r_.get('fanouts'), r_['relocs'][-1], r_.get('error', ''), flush=True)
    ok = [r_ for r_ in res if r_.get('cts_area') is not None and r_.get('held')]
    if not ok: break
    cand = min(ok, key=lambda r_: r_['cts_area'])
    if cand['cts_area'] >= best['cts_area'] - 1e-6:
        print('no improvement in round', rnd, flush=True); break
    best = cand
    json.dump({'best': best, 'log': log}, open(os.path.join(root, 'logs', f'cts_search_{a.tag}.json'), 'w'), indent=1)
json.dump({'best': best, 'log': log}, open(os.path.join(root, 'logs', f'cts_search_{a.tag}.json'), 'w'), indent=1)
print('BEST', best['tag'], best['cts_area'], best['relocs'], flush=True)
