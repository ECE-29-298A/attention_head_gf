#!/usr/bin/env python3
"""Netlist-agnostic datapath attribution (no instance names, no hierarchy): flops by the public
name of their Q net, combinational cells by the flops their fan-out cone reaches (then fan-in).

dp flops (216 in h2 and x0): Q net core.mac.ring[*] (ring tail), core.divider_unit.sum_in[*] and
core.divider_unit.magnitude[0] (ring head O0, named after the divider input it feeds),
core.exponent_unit.D[*] (mac S register, named after the exp_lut input), core.mac.M[*] (max_reg M),
core.divider_unit.denominator[*] (mac L register, named after the divider input).
A combinational cell is dp when the flops reached by its fan-out cone (depth <= 8, through
combinational cells, nets of fanout <= 24 beyond the cell's own output, weight 1/depth) are mostly dp flops; a cell whose cone
reaches no flop uses its fan-in cone instead.
usage: attribute.py <synth .nl.v> [--compare B_attribution.json] [--json OUT]"""
import sys, os, re, json, collections, argparse
DP_Q = re.compile(r'^(core\.mac\.ring\[|core\.divider_unit\.sum_in\[|core\.divider_unit\.magnitude\[0\]|'
                  r'core\.exponent_unit\.D\[|core\.mac\.M\[|core\.divider_unit\.denominator\[)')
DP_LABELS = ('core.mac', 'core.mac.adder', 'core.mac.l_adder', 'core.max_unit', 'core.exponent_unit')


def parse_nl(path):
    """{inst: (master_short, {pin: net})} from a Yosys structural netlist (escaped names unescaped)."""
    txt = open(path).read()
    out = {}
    for m in re.finditer(r'^\s*gf180mcu_fd_sc_mcu7t5v0__(\w+)\s+(\S+)\s*\((.*?)\);', txt, re.S | re.M):
        mst, inst, body = m.groups()
        pins = {}
        for p, net in re.findall(r'\.(\w+)\s*\(\s*([^()]*?)\s*\)', body):
            net = net.strip().lstrip('\\').strip()
            if net and not re.match(r"^\d+'[bh]", net):
                pins[p] = net
        out[inst.lstrip('\\')] = (mst, pins)
    return out


def attribute(cells, pdir, clk='clk', boundary=False):
    """cells: {inst: (master, {pin: net})}; pdir(master, pin) -> 'input'/'output'.
    Returns {inst: 'dp' | 'other' | 'tie'} and {inst: how}."""
    drv, sinks = {}, collections.defaultdict(list)
    for n, (m, pins) in cells.items():
        for p, net in pins.items():
            if net == clk: continue
            if pdir(m, p) == 'output': drv[net] = n
            else: sinks[net].append(n)
    isff = {n: m.startswith(('dff', 'sdff')) for n, (m, _) in cells.items()}
    lab, how = {}, {}
    for n, (m, pins) in cells.items():
        if m.startswith('tie'):
            lab[n], how[n] = 'tie', 'tie'
        elif isff[n]:
            q = pins.get('Q', '')
            lab[n], how[n] = ('dp' if DP_Q.match(q) else 'other'), 'flop-q'
    outs = {n: [net for p, net in pins.items() if pdir(m, p) == 'output' and net != clk] for n, (m, pins) in cells.items()}
    ins = {n: [net for p, net in pins.items() if pdir(m, p) != 'output' and net != clk] for n, (m, pins) in cells.items()}

    def cone(n, forward):
        score = collections.Counter(); seen = {n}; front = [n]
        for depth in range(1, 9):
            nxt = []
            for c in front:
                nets = outs[c] if forward else ins[c]
                for net in nets:
                    nb = sinks.get(net, []) if forward else ([drv[net]] if net in drv else [])
                    if forward and depth > 1 and len(nb) > 24: continue
                    for k in nb:
                        if k in seen: continue
                        seen.add(k)
                        if isff[k]: score[lab[k]] += 1.0 / depth
                        elif not cells[k][0].startswith('tie'): nxt.append(k)
            front = nxt
            if not front: break
        return score
    for n in cells:
        if n in lab: continue
        s = cone(n, True); h = 'fanout-cone'
        if not s:
            s = cone(n, False); h = 'fanin-cone'
        lab[n] = 'dp' if s.get('dp', 0) > s.get('other', 0) else 'other'
        how[n] = h
    # optional boundary (off by default; on h2 it pulls in 71 divider front-end cells): a combinational cell whose fan-out cone is mostly other flops but whose fan-in cone
    # is mostly dp flops (the datapath's outputs into the divider / control) -> 'dpb'
    for n in (cells if boundary else ()):
        if lab[n] != 'other' or isff[n] or how[n] != 'fanout-cone': continue
        s = cone(n, False)
        if s and s.get('dp', 0) > s.get('other', 0):
            lab[n], how[n] = 'dpb', 'fanin-cone (boundary)'
    return lab, how


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import dplib
    ap = argparse.ArgumentParser(); ap.add_argument('nl'); ap.add_argument('--compare'); ap.add_argument('--json'); a = ap.parse_args()
    C = parse_nl(a.nl); LIB = dplib.liberty()
    pdir = lambda m, p: LIB[m]['pins'].get(p, {}).get('dir')
    lab, how = attribute(C, pdir)
    cnt = collections.Counter(lab.values())
    print('cells', len(C), dict(cnt), 'dp flops', sum(1 for n in lab if lab[n] == 'dp' and C[n][0].startswith('dff')),
          'cluster (dp+dpb)', sum(1 for v in lab.values() if v in ('dp', 'dpb')))
    res = {'netlist': a.nl, 'netlist_sha16': dplib.sha(a.nl), 'counts': dict(cnt), 'labels': lab, 'how': how}
    if a.compare:
        B = json.load(open(a.compare))['cells']
        isdp = lambda v: v in ('dp', 'dpb')
        agree = sum(1 for n in lab if n in B and (B[n]['label'] in DP_LABELS) == isdp(lab[n]))
        dis = [(n, C[n][0], B[n]['label'], lab[n]) for n in lab if n in B and lab[n] != 'tie' and (B[n]['label'] in DP_LABELS) != isdp(lab[n])]
        print(f'agreement with {a.compare}: {agree}/{len(lab)}; disagreements {len(dis)}')
        print('  ', collections.Counter((b, l) for _, _, b, l in dis))
        res['compare'] = {'file': a.compare, 'agree': agree, 'disagree': dis}
    if a.json: json.dump(res, open(a.json, 'w'), indent=1)
