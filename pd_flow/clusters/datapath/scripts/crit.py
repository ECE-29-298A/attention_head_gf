#!/usr/bin/env python3
"""Driver criticality per net (D10 cost item 4): how close each driver is to its slew / cap limit.

  load C = sum of sink pin caps (ss_125C_3v00 Liberty) + c_w x HPWL (pin centres, at a placement)
  slew   = max over the driver's arcs of the Liberty rise/fall_transition table at (tin, C)
  crit   = max(slew / MAX_TRANSITION, C / min(max_capacitance, MAX_CAPACITANCE), fanout / MAX_FANOUT)

Two wire models, both measured, both reported:
  rsz : the resizer's placement-time model (LAYERS_RC unset -> tech-LEF CPERSQDIST x Metal2 width);
  sig : signoff, the effective per-HPWL-um wire cap of the h2 max-corner SPEF (*D_NET total, which is wire
        only), C_net / HPWL, median over unbuffered nets (driver not repaired in h2) with HPWL >= 20 um.
usage: crit.py [--placement DIR] [--tin 1.0] [--json OUT]   (default placement: the seed, h2 final)"""
import sys, os, re, json, glob, bisect, argparse, statistics
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib
PDKV = '/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee'
LIB_SS = PDKV + '/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__ss_125C_3v00.lib'
TLEF = PDKV + '/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/techlef/gf180mcu_fd_sc_mcu7t5v0__nom.tlef'
MAX_TRAN, MAX_CAP, MAX_FO = 3.0, 0.2, 20


def block(text, i):
    """text[i] == '{' -> index after the matching '}' (brace tokenizer, comments and strings skipped)"""
    depth, k, n = 0, i, len(text)
    while k < n:
        ch = text[k]
        if ch == '"':
            k = text.index('"', k + 1)
        elif text.startswith('/*', k):
            k = text.index('*/', k) + 1
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: return k + 1
        k += 1
    raise ValueError('unbalanced')


def children(body, kw):
    """[(arg, body)] for every `kw(arg) { ... }` at any depth inside body"""
    out = []
    for m in re.finditer(r'\b' + kw + r'\s*\(\s*"?([^")]*)"?\s*\)\s*\{', body):
        j = block(body, m.end() - 1); out.append((m.group(1), body[m.end():j - 1]))
    return out


def table(body):
    i1 = [float(v) for v in re.search(r'index_1\s*\(\s*"([^"]+)"', body).group(1).split(',')]
    i2 = [float(v) for v in re.search(r'index_2\s*\(\s*"([^"]+)"', body).group(1).split(',')]
    vals = [[float(v) for v in row.split(',')] for row in re.findall(r'"([^"]+)"', re.search(r'values\s*\((.*?)\)\s*;', body, re.S).group(1))]
    assert len(vals) == len(i1) and all(len(r) == len(i2) for r in vals), 'degenerate table'
    return i1, i2, vals


def interp(t, x, y):
    i1, i2, v = t
    def bracket(ax, q):
        k = min(max(bisect.bisect_left(ax, q), 1), len(ax) - 1); return k - 1, k
    a0, a1 = bracket(i1, x); b0, b1 = bracket(i2, y)
    fx = (x - i1[a0]) / (i1[a1] - i1[a0]); fy = (y - i2[b0]) / (i2[b1] - i2[b0])
    return (v[a0][b0] * (1 - fx) * (1 - fy) + v[a1][b0] * fx * (1 - fy) + v[a0][b1] * (1 - fx) * fy + v[a1][b1] * fx * fy)


def liberty_ss(masters):
    text = open(LIB_SS).read(); out = {}
    for m in sorted(masters):
        k = text.find(f'cell({dplib.PFX}{m})')
        if k < 0: k = text.find(f'cell("{dplib.PFX}{m}")')
        assert k >= 0, m
        b = text[text.index('{', k) + 1:block(text, text.index('{', k)) - 1]
        pins = {}
        for pn, pb in children(b, 'pin'):
            d = re.search(r'direction\s*:\s*"?(\w+)', pb).group(1)
            if d == 'input':
                pins[pn] = {'dir': d, 'cap': float(re.search(r'\bcapacitance\s*:\s*([0-9.eE+-]+)', pb).group(1))}
            elif d == 'output':
                mc = re.search(r'max_capacitance\s*:\s*([0-9.eE+-]+)', pb)
                tabs = []
                for _, tb in children(pb, 'timing'):
                    for kw in ('rise_transition', 'fall_transition'):
                        for _, xb in children(tb, kw): tabs.append(table(xb))
                pins[pn] = {'dir': d, 'max_cap': float(mc.group(1)) if mc else None, 'tran': tabs}
        out[m] = pins
    assert out and all(any(p['dir'] == 'output' and p['tran'] for p in v.values()) for k, v in out.items()
                       if not k.startswith(('tie', 'fill', 'endcap', 'antenna'))), 'liberty parse degenerate'
    return out


def wire_cap_rsz():
    t = open(TLEF).read(); s = t[t.index('LAYER Metal2'):]; s = s[:s.index('END Metal2')]
    cpsq = float(re.search(r'CAPACITANCE CPERSQDIST\s+([0-9.eE+-]+)', s).group(1))
    w = float(re.search(r'\n\s*WIDTH\s+([0-9.]+)', s).group(1))
    edge = re.search(r'EDGECAPACITANCE\s+([0-9.eE+-]+)', s)
    return cpsq * w + (2 * float(edge.group(1)) if edge else 0.0), {'CPERSQDIST': cpsq, 'width': w, 'EDGECAPACITANCE': edge.group(1) if edge else None}


def wire_cap_sig(d, LIBS):
    sp = glob.glob(dplib.REF + '/54-openroad-rcx/max/*.spef')[0]
    names = {}; caps = {}; mode = None
    for line in open(sp):
        if line.startswith('*NAME_MAP'): mode = 'map'; continue
        if mode == 'map':
            if line.startswith('*') and len(line.split()) == 2 and line.split()[0][1:].isdigit():
                k, v = line.split(); names[k] = v.replace('\\', ''); continue
            elif line.strip(): mode = None
        if line.startswith('*D_NET'):
            _, nm, c = line.split()[:3]; caps[names.get(nm, nm).replace('\\', '')] = float(c)
    W = dplib.Wire(dplib.seed_from_h2(d)); ratios = []
    H = json.load(open(os.path.join(here, '..', 'baseline', ('h2_area_classes.json' if dplib.REF_TAG == 'h2' else dplib.REF_TAG + '_area_classes.json'))))
    rep = set(H['repair_by_driver'])
    for b, lst in d.nets.items():
        if b == d.clk or b not in caps or b not in d.driver or d.driver[b][0] in rep: continue
        L = W.net(b)
        if L < 20: continue
        ratios.append(caps[b] / L)
    return statistics.median(ratios), {'spef': sp, 'nets_used': len(ratios), 'p25': statistics.quantiles(ratios, n=4)[0],
                                       'p75': statistics.quantiles(ratios, n=4)[2]}


def criticality(d, P, LIBS, cw, tin=1.0):
    W = dplib.Wire(P); out = {}
    for b, lst in d.nets.items():
        if b == d.clk or b not in d.driver: continue
        n0, p0 = d.driver[b]
        drv = LIBS.get(d.master[n0], {}).get(p0)
        if not drv or not drv.get('tran'): continue
        cp = sum(LIBS.get(d.master[n], {}).get(p, {}).get('cap', 0.0) for n, p in lst if (n, p) != (n0, p0))
        L = W.net(b); C = cp + cw * L
        slew = max(interp(t, tin, C) for t in drv['tran'])
        mc = min(drv['max_cap'] or MAX_CAP, MAX_CAP)
        out[b] = {'driver': n0, 'master': d.master[n0], 'fanout': len(lst) - 1, 'hpwl': round(L, 1), 'C_pF': round(C, 5),
                  'slew_ns': round(slew, 3), 'crit': round(max(slew / MAX_TRAN, C / mc, (len(lst) - 1) / MAX_FO), 3)}
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--placement'); ap.add_argument('--tin', type=float, default=1.0); ap.add_argument('--json')
    a = ap.parse_args(); d = dplib.Design()
    LIBS = liberty_ss(set(d.master.values()) | {c['master'] for c in d.D['comps'].values() if c['master'] in d.LEFS})
    crsz, rinfo = wire_cap_rsz(); csig, sinfo = wire_cap_sig(d, LIBS)
    P = dplib.Placement.load(d, a.placement) if a.placement else dplib.seed_from_h2(d)
    R = criticality(d, P, LIBS, crsz, a.tin); S = criticality(d, P, LIBS, csig, a.tin)
    print(f'wire cap: resizer model {crsz * 1e3:.4f} fF/um {rinfo}; signoff effective {csig * 1e3:.4f} fF/um (median, {sinfo["nets_used"]} nets, '
          f'IQR {sinfo["p25"] * 1e3:.4f}-{sinfo["p75"] * 1e3:.4f})')
    for tag, X in (('rsz', R), ('sig', S)):
        v = sorted(X.values(), key=lambda r: -r['crit'])
        print(f'{tag}: nets {len(v)}, crit>=1: {sum(1 for r in v if r["crit"] >= 1)}, >=0.7: {sum(1 for r in v if r["crit"] >= 0.7)}, '
              f'slew>=3ns: {sum(1 for r in v if r["slew_ns"] >= 3)}')
        for r in v[:8]: print('   ', r)
    if a.json: json.dump({'wire_cap_rsz_pF_per_um': crsz, 'rsz_info': rinfo, 'wire_cap_sig_pF_per_um': csig, 'sig_info': sinfo,
                          'tin_ns': a.tin, 'rsz': R, 'sig': S}, open(a.json, 'w'), indent=1)
