#!/usr/bin/env python3
"""Collect chip-tetris results into results.json from dry-run summaries (wc_work/<tag>_{r32,firm,cts}/summary.json),
the reference runs' final metrics, and signoff runs.  Input: results_config.json
  {"reference": "<run>", "record_reference": "<run>", "x0": "<run>",
   "groups": {"<group>": [["<tag>", "<work dir>", "<note>"], ...]}, "packing": [...tags...], "signoff": {...}}
usage: make_results.py results_config.json results.json"""
import sys, os, json, glob
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib, compare


def ref_block(run, tag):
    m = compare._ref_metrics(run); M = json.load(open(os.path.join(run, 'final', 'metrics.json')))
    ac = os.path.join(here, '..', 'baseline', f'{tag}_area_classes.json')
    out = {'run': run, 'metrics_json': os.path.join(run, 'final', 'metrics.json'), **m,
           'route_drc': M.get('route__drc_errors'), 'antenna_nets': M.get('antenna__violating__nets'),
           'magic_drc': M.get('magic__drc_error__count'), 'lvs_errors': M.get('design__lvs_error__count'),
           'power_total_W': M.get('power__total'),
           'per_corner': {k.split('corner:')[1]: {'setup': v, 'hold': M['timing__hold__ws__corner:' + k.split('corner:')[1]]}
                          for k, v in M.items() if k.startswith('timing__setup__ws__corner:')},
           'synth_area': json.load(open(glob.glob(os.path.join(run, '06-*', 'state_out.json'))[0]))['metrics'].get('design__instance__area')}
    if os.path.exists(ac):
        A = json.load(open(ac)); out['area_classes'] = {k: v['area'] for k, v in A['classes'].items()}; out['area_classes_json'] = os.path.abspath(ac)
    return out


cfg = json.load(open(sys.argv[1])); res = {'objective': 'design__instance__area__stdcell (D10)', 'references': {}}
for k in ('reference', 'record_reference', 'x0', 'other'):
    for tag, run in (cfg.get(k) or {}).items():
        res['references'][tag] = {'role': k, **ref_block(run, tag)}
for g, rows in cfg['groups'].items():
    res[g] = []
    for tag, work, note in rows:
        s = json.load(open(work if work.endswith('.json') else os.path.join(work, 'summary.json')))
        r = compare.row(s) if s.get('metrics') else {'tag': tag, 'cts_census': {k: s.get('cts', {}).get(k) for k in ('cts_area', 'n_leaves', 'dummies', 'masters')}}
        r.update({'tag': tag, 'note': note, 'work': work, 'mode': s.get('mode'), 'placement_dir': s.get('placement_dir')})
        gj = os.path.join(s.get('placement_dir', ''), 'gen.json')
        if os.path.exists(gj):
            G = json.load(open(gj)); r['footprint'] = G.get('footprint'); r['gen_args'] = G.get('args'); r['hpwl_pins_um'] = G.get('hpwl_pins_um')
        res[g].append(r)
for k in ('packing_sequence', 'signoff', 'robustness', 'notes'):
    if k in cfg: res[k] = cfg[k]
json.dump(res, open(sys.argv[2], 'w'), indent=1)
print('wrote', sys.argv[2], {g: len(v) for g, v in res.items() if isinstance(v, list)})
