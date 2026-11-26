#!/usr/bin/env python3
"""Signoff summary of a finished LibreLane run from final/metrics.json (+ synthesized netlist hash).
usage: run_summary.py <run_dir> [--json OUT]"""
import sys, os, json, glob, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdlib import sha
ap = argparse.ArgumentParser(); ap.add_argument('run'); ap.add_argument('--json'); a = ap.parse_args()
M = json.load(open(os.path.join(a.run, 'final', 'metrics.json')))
g = lambda k: M.get(k)
corners = sorted({k.split('__corner:')[1] for k in M if '__corner:' in k})
out = {'run': a.run, 'metrics_sha16': sha(os.path.join(a.run, 'final', 'metrics.json')),
       'synth_nl_sha16': sha(glob.glob(os.path.join(a.run, '*-yosys-synthesis', '*.nl.v'))[0]),
       'stdcell_area': g('design__instance__area__stdcell'), 'core_area': g('design__core__area'),
       'utilization': g('design__instance__utilization'),
       'magic_drc': g('magic__drc_error__count'), 'klayout_drc': g('klayout__drc_error__count'),
       'route_drc': g('route__drc_errors'), 'lvs_errors': g('design__lvs_error__count'),
       'lvs_unmatched_devices': g('design__lvs_unmatched_device__count'), 'lvs_unmatched_nets': g('design__lvs_unmatched_net__count'),
       'antenna_nets': g('antenna__violating__nets'), 'antenna_pins': g('antenna__violating__pins'),
       'illegal_overlap': g('magic__illegal_overlap__count'), 'disconnected_pins': g('design__disconnected_pin__count'),
       'wirelength_um': g('route__wirelength'), 'vias': g('route__vias'),
       'slew_violations': g('design__max_slew_violation__count'), 'cap_violations': g('design__max_cap_violation__count'),
       'fanout_violations': g('design__max_fanout_violation__count'),
       'setup_ws_min': min((v for k, v in M.items() if k.startswith('timing__setup__ws__corner:')), default=None),
       'hold_ws_min': min((v for k, v in M.items() if k.startswith('timing__hold__ws__corner:')), default=None),
       'power_total_W': g('power__total'), 'instance_count': g('design__instance__count'),
       'per_corner': {c: {'setup_ws': g(f'timing__setup__ws__corner:{c}'), 'hold_ws': g(f'timing__hold__ws__corner:{c}'),
                          'slew': g(f'design__max_slew_violation__count__corner:{c}'), 'cap': g(f'design__max_cap_violation__count__corner:{c}'),
                          'fanout': g(f'design__max_fanout_violation__count__corner:{c}')} for c in corners}}
for k, v in out.items():
    if k != 'per_corner': print(f'{k:24s} {v}')
for c, v in out['per_corner'].items(): print(f'  {c:20s} {v}')
if a.json: json.dump(out, open(a.json, 'w'), indent=1)
