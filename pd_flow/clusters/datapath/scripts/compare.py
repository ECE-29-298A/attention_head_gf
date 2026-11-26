#!/usr/bin/env python3
"""Compare FIRM dry-run summaries against h2 (and each other): gate, area by class, repaired drivers.
usage: compare.py <summary.json> [...]      (summary.json from dryrun.py / pipeline.py)
Gate (D2/D6/D8 + mechanism), against the reference run (env DP_REF: h2 or x0): stdcell < ref; slew/cap/fanout <= ref's; setup and hold >= 0 at
every corner; route DRC 0; antenna 0; every custom cell held at every step; no reservation miss."""
import sys, os, json
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib
_REFS = {
    'h2': {'classes': 'h2_area_classes.json', 'run': dplib.H2,
           'M': {'stdcell_area': 45475.8, 'slew': 281, 'cap': 2, 'fanout': 6, 'setup_ws_min': 41.7919, 'hold_ws_min': 0.0576,
                 'wirelength_um': 50554}},
    'x0': {'classes': 'x0_area_classes.json', 'run': dplib.X0RUN,
           'M': {'stdcell_area': 44911.6, 'slew': 242, 'cap': 1, 'fanout': 0, 'setup_ws_min': 43.1557, 'hold_ws_min': 0.00695,
                 'wirelength_um': 49125}}}
REFTAG = dplib.REF_TAG if dplib.REF_TAG in _REFS else 'h2'
H2 = json.load(open(os.path.join(here, '..', 'baseline', _REFS[REFTAG]['classes'])))   # reference area classes
H2M = _REFS[REFTAG]['M']                                                                # reference signoff metrics
KEYS = ('upsize', 'repair', 'cts', 'hold', 'antenna')


def gate(s):
    m = s.get('metrics') or {}
    if not m: return False, ['no metrics (chain failed?)']
    why = []
    if not m['stdcell_area'] < H2M['stdcell_area']: why.append(f"area {m['stdcell_area']}")
    if m['slew'] > H2M['slew']: why.append(f"slew {m['slew']}")
    if m['cap'] > H2M['cap']: why.append(f"cap {m['cap']}")
    if m['fanout'] > H2M['fanout']: why.append(f"fanout {m['fanout']}")
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
    return {'tag': os.path.basename(s['work']).replace('_firm', ''), 'area': m.get('stdcell_area'),
            'd_area': round(m['stdcell_area'] - H2M['stdcell_area'], 2) if m else None,
            'd_upsize': round(cl['upsize'] - h['upsize'], 2), 'd_repair': round(cl['repair'] - h['repair'], 2),
            'd_cts': round(cl['cts'] - h['cts'], 2), 'd_hold': round(cl['hold'] - h['hold'], 2),
            'slew_cap_fo': f"{m.get('slew')}/{m.get('cap')}/{m.get('fanout')}", 'setup': m.get('setup_ws_min'),
            'hold': m.get('hold_ws_min'), 'wire': m.get('wirelength_um'), 'drc': m.get('route_drc'),
            'ant': m.get('antenna_nets'), 'held': s.get('ALL_HELD'),
            'rep_drivers': s.get('area_classes', {}).get('repaired_drivers'),
            'rep_drivers_dp': s.get('area_classes', {}).get('repaired_drivers_dp'),
            'cts_masters': s.get('area_classes', {}).get('cts_masters'), 'pass': ok, 'why': why}


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
