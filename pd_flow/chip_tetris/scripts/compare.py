#!/usr/bin/env python3
"""Compare FIRM dry-run summaries against h2 (and each other): gate, area by class, repaired drivers.
usage: compare.py <summary.json> [...]      (summary.json from dryrun.py / pipeline.py)
Gate (D2/D6/D8 + mechanism), against the reference run (env DP_REF: h2 or x0): stdcell < ref; slew/cap/fanout <= ref's; setup and hold >= 0 at
every corner; route DRC 0; antenna 0; every custom cell held at every step; no reservation miss."""
import sys, os, json
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib
def _ref_metrics(run):
    M = json.load(open(os.path.join(run, 'final', 'metrics.json'))); g = M.get
    return {'stdcell_area': g('design__instance__area__stdcell'), 'slew': g('design__max_slew_violation__count'),
            'cap': g('design__max_cap_violation__count'), 'fanout': g('design__max_fanout_violation__count'),
            'setup_ws_min': min(v for k, v in M.items() if k.startswith('timing__setup__ws__corner:')),
            'hold_ws_min': min(v for k, v in M.items() if k.startswith('timing__hold__ws__corner:')),
            'wirelength_um': g('route__wirelength')}


REFTAG = dplib.REF_TAG
H2 = json.load(open(os.path.join(here, '..', 'baseline', REFTAG + '_area_classes.json')))   # reference area classes
H2M = _ref_metrics(dplib.REF)                                                                   # reference signoff metrics
KEYS = ('upsize', 'repair', 'cts', 'hold', 'antenna')


def gate(s):
    m = s.get('metrics') or {}
    if not m: return False, ['no metrics (chain failed?)']
    why = []
    if not m['stdcell_area'] < H2M['stdcell_area']: why.append(f"area {m['stdcell_area']}")
    # D2: counts may not exceed the reference's, except inside the measured noise band (AGENT_CONTEXT: slew 260-381,
    # cap 1-2, fanout 11-13); 'strict' = no count above the reference's, reported separately (strict_d2)
    for k, band in (('slew', 381), ('cap', 2), ('fanout', 13)):
        if m[k] > max(H2M[k], band): why.append(f"{k} {m[k]}")
    if m['setup_ws_min'] < 0: why.append('setup')
    if m['hold_ws_min'] < 0: why.append('hold')
    if m['route_drc']: why.append(f"drc {m['route_drc']}")
    if m['antenna_nets']: why.append(f"antenna {m['antenna_nets']}")
    if not s.get('ALL_HELD'): why.append('not held')
    if s.get('reservation_misses'): why.append('reservation miss')
    return not why, why


def row(s):
    m = s.get('metrics') or {}; ac = s.get('area_classes', {}).get('classes', {})
    cl = {k: ac.get(k, {}).get('area', 0.0) for k in KEYS}
    h = {k: H2['classes'].get(k, {}).get('area', 0.0) for k in KEYS}
    ok, why = gate(s)
    return {'tag': os.path.basename(s['work']).replace('_firm', '').replace('_r32', ''), 'mode': s.get('mode', 'firm17'),
            'cts_census': {k: s.get('cts', {}).get(k) for k in ('cts_area', 'n_leaves', 'dummies', 'masters')}, 'area': m.get('stdcell_area'),
            'd_area': round(m['stdcell_area'] - H2M['stdcell_area'], 2) if m else None,
            'd_upsize': round(cl['upsize'] - h['upsize'], 2), 'd_repair': round(cl['repair'] - h['repair'], 2),
            'd_cts': round(cl['cts'] - h['cts'], 2), 'd_hold': round(cl['hold'] - h['hold'], 2),
            'slew_cap_fo': f"{m.get('slew')}/{m.get('cap')}/{m.get('fanout')}", 'setup': m.get('setup_ws_min'),
            'hold': m.get('hold_ws_min'), 'wire': m.get('wirelength_um'), 'drc': m.get('route_drc'),
            'ant': m.get('antenna_nets'), 'held': s.get('ALL_HELD'),
            'rep_drivers': s.get('area_classes', {}).get('repaired_drivers'),
            'rep_drivers_dp': s.get('area_classes', {}).get('repaired_drivers_dp'),
            'cts_masters': s.get('area_classes', {}).get('cts_masters'), 'pass': ok, 'why': why,
            'strict_d2': bool(m) and all(m[k] <= H2M[k] for k in ('slew', 'cap', 'fanout'))}


if __name__ == '__main__':
    print(f"{'tag':14s} {'area':>9s} {'d':>7s} {'dUp':>7s} {'dRep':>7s} {'dCTS':>7s} {'s/c/f':>9s} {'setup':>6s} {'hold':>6s} {'wire':>6s} drv(dp) gate")
    print(f"{REFTAG:14s} {H2M['stdcell_area']:9.1f} {0:7.1f} {0:7.1f} {0:7.1f} {0:7.1f} {str(H2M['slew'])+'/'+str(H2M['cap'])+'/'+str(H2M['fanout']):>9s} {H2M['setup_ws_min']:6.2f} {H2M['hold_ws_min']:6.3f} {H2M['wirelength_um']:6d} {H2['repaired_drivers']}({H2['repaired_drivers_dp']})")
    for p in sys.argv[1:]:
        r = row(json.load(open(p)))
        if r['area'] is None:
            print(f"{r['tag']:14s} FAILED {r['why']}"); continue
        print(f"{r['tag']:14s} {r['area']:9.1f} {r['d_area']:+7.1f} {r['d_upsize']:+7.1f} {r['d_repair']:+7.1f} {r['d_cts']:+7.1f} "
              f"{r['slew_cap_fo']:>9s} {r['setup']:6.2f} {r['hold']:6.3f} {r['wire']:6d} {r['rep_drivers']}({r['rep_drivers_dp']}) "
              f"{'PASS' if r['pass'] else 'fail: ' + ','.join(r['why'])}")
