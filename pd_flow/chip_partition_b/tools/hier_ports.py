#!/usr/bin/env python3
"""Hierarchical port widths and per-pair connection widths from a hierarchy-kept netlist JSON.
usage: hier_ports.py <keep_all_vnames.json> [--json OUT]
For every parent module, each net bit is classified by which child-instance ports (and the parent's
own cells / own ports) touch it; a bit driven by child A (output port) and read by child B (input
port) counts as A->B.  Instance paths are relative to the top (e.g. core.mac.adder)."""
import json, sys, argparse, collections
ap = argparse.ArgumentParser(); ap.add_argument('netlist'); ap.add_argument('--json')
a = ap.parse_args()
M = json.load(open(a.netlist))['modules']
user = {m: v for m, v in M.items() if not m.startswith('gf180mcu') and v.get('cells') is not None and not v.get('attributes', {}).get('blackbox')}
top = [m for m, v in user.items() if v.get('attributes', {}).get('top')] or ['tt_um_attention_head_gf']
top = top[0]
INST = {'tt_um_attention_head_gf': 'top'}
res = {'modules': {}, 'pairs': []}
def short(m):
    for k in ('attention_controller', 'divider', 'exp_lut', 'mac_unit', 'ripple_add', 'max_reg'):
        if k in m: return k
    return m
def walk(mod, path):
    v = user[mod]
    kids = {n: c for n, c in v['cells'].items() if c['type'] in user}
    ports = {p: (d['direction'], len(d['bits'])) for p, d in v['ports'].items()}
    res['modules'][path] = {'module': short(mod), 'in_bits': sum(w for d, w in ports.values() if d == 'input'),
                            'out_bits': sum(w for d, w in ports.values() if d == 'output'), 'ports': ports}
    # bit -> list of (endpoint, dir)
    touch = collections.defaultdict(list)
    for p, d in v['ports'].items():
        for b in d['bits']:
            if isinstance(b, int): touch[b].append(('PARENT_PORT', 'src' if d['direction'] == 'input' else 'snk'))
    for n, c in v['cells'].items():
        if c['type'] in user:
            cp = user[c['type']]['ports']
            ep = (path + '.' if path != 'top' else '') + n.split('.')[-1].lstrip('\\')
            for pn, bits in c['connections'].items():
                dr = cp[pn]['direction']
                for b in bits:
                    if isinstance(b, int): touch[b].append((ep, 'src' if dr == 'output' else 'snk'))
        else:
            pd = c.get('port_directions', {})
            for pn, bits in c['connections'].items():
                for b in bits:
                    if isinstance(b, int): touch[b].append(('OWN:' + path, 'src' if pd.get(pn) == 'output' else 'snk'))
    pair = collections.Counter()
    for b, eps in touch.items():
        srcs = {e for e, d in eps if d == 'src'}; snks = {e for e, d in eps if d == 'snk'}
        for s in srcs:
            for t in snks:
                if s != t: pair[(s, t)] += 1
    for (s, t), w in sorted(pair.items(), key=lambda x: -x[1]):
        res['pairs'].append({'parent': path, 'from': s, 'to': t, 'bits': w})
    for n, c in kids.items():
        walk(c['type'], (path + '.' if path != 'top' else '') + n.split('.')[-1].lstrip('\\'))
walk(top, 'top')
for p, m in res['modules'].items():
    print(f"{p:28s} {m['module']:22s} in {m['in_bits']:4d} out {m['out_bits']:4d}")
print()
for r in res['pairs']:
    if 'OWN' in r['from'] and 'OWN' in r['to']: continue
    print(f"  [{r['parent']}] {r['from']:28s} -> {r['to']:28s} {r['bits']:4d} bits")
if a.json: json.dump(res, open(a.json, 'w'), indent=1)
