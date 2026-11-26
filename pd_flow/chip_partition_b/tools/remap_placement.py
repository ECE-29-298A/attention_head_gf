#!/usr/bin/env python3
"""Carry a placement from netlist A to a re-synthesized netlist B whose instance numbering changed.
Flops are matched by their Q net's public name (stable across re-synthesis); combinational cells by
iterative structural matching (same master, same pin -> already-matched driver for every input),
forward from flops/ports.  Unmatched B cells are listed for re-placement by the region placer.
usage: remap_placement.py <placement.json> --from A.json --to B.json [--out OUT.json]"""
import sys, os, json, argparse, collections
ap = argparse.ArgumentParser(); ap.add_argument('placement'); ap.add_argument('--from', dest='fa', required=True)
ap.add_argument('--to', dest='fb', required=True); ap.add_argument('--out'); a = ap.parse_args()
def load(p):
    M = json.load(open(p))['modules']['tt_um_attention_head_gf']
    names = collections.defaultdict(list)
    for n, v in M['netnames'].items():
        if v.get('hide_name') or n.startswith('_') or n.startswith('$'): continue
        for i, b in enumerate(v['bits']): names[b].append(n if len(v['bits']) == 1 else f'{n}[{i}]')
    drv = {}
    for cn, c in M['cells'].items():
        for pin, bits in c['connections'].items():
            if c.get('port_directions', {}).get(pin) == 'output':
                for b in bits: drv[b] = (cn, pin)
    for pn, pd in M['ports'].items():
        if pd['direction'] == 'input':
            for i, b in enumerate(pd['bits']): drv[b] = ('PORT', f'{pn}[{i}]')
    return M, names, drv
A, nA, dA = load(a.fa); B, nB, dB = load(a.fb)
P = json.load(open(a.placement))['cells']
isff = lambda c: c['type'].split('__')[1].startswith(('dff', 'sdff'))
mp = {}
qa = {}
for cn, c in A['cells'].items():
    if isff(c):
        for b in c['connections'].get('Q', []): 
            for nm in nA.get(b, []): qa[nm] = cn
for cn, c in B['cells'].items():
    if isff(c):
        hits = {qa[nm] for b in c['connections'].get('Q', []) for nm in nB.get(b, []) if nm in qa}
        if len(hits) == 1:
            x = hits.pop()
            if A['cells'][x]['type'] == c['type'] or True: mp[cn] = x
nff = len(mp); ffB = sum(1 for c in B['cells'].values() if isff(c))
inv = {v: k for k, v in mp.items()}
def key(M, cn, drv, m):
    c = M['cells'][cn]; ks = []
    for pin, bits in sorted(c['connections'].items()):
        if c.get('port_directions', {}).get(pin) != 'input': continue
        for b in bits:
            if not isinstance(b, int): ks.append((pin, 'CONST', b)); continue
            d = drv.get(b)
            if d is None: return None
            if d[0] == 'PORT': ks.append((pin, d)); continue
            t = m.get(d[0])
            if t is None: return None
            ks.append((pin, t, d[1]))
    return (c['type'].split('__')[1], tuple(ks))
for it in range(200):
    idxA = collections.defaultdict(list)
    ident = {k: k for k in inv}           # A-side cells map to themselves in A's key space
    for cn in A['cells']:
        if cn in inv: continue
        k = key(A, cn, dA, {x: x for x in A['cells'] if x in inv})
        if k: idxA[k].append(cn)
    new = 0
    for cn in B['cells']:
        if cn in mp: continue
        k = key(B, cn, dB, mp)
        if k and len(idxA.get(k, [])) == 1:
            x = idxA[k][0]
            if x not in inv: mp[cn] = x; inv[x] = cn; new += 1
    if not new: break
out = {}
for cn, x in mp.items():
    if x in P: out[cn] = dict(P[x], master=B['cells'][cn]['type'].split('__')[1], from_inst=x)
unB = [cn for cn in B['cells'] if cn not in mp and not B['cells'][cn]['type'].split('__')[1].startswith('tie')]
res = {'flops_B': ffB, 'flops_mapped': nff, 'cells_B': len(B['cells']), 'cells_mapped': len(mp),
       'placed_carried': len(out), 'unmatched_B_nontie': len(unB),
       'master_changed': sum(1 for cn, x in mp.items() if A['cells'][x]['type'] != B['cells'][cn]['type'])}
print(json.dumps(res))
if a.out: json.dump({'summary': res, 'cells': out, 'unmatched': unB}, open(a.out, 'w'), indent=1)
