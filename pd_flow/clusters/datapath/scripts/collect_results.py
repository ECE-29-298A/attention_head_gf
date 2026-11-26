#!/usr/bin/env python3
"""Collect every screened candidate into results.json (each number with the run it came from).
usage: collect_results.py <out results.json> <tag>=<placement_dir> [...]
Reads <placement_dir>/firm_summary.json (dryrun.py FIRM summary, its 'work' is the run) and gen.json."""
import sys, os, json, glob
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import compare
H2RUN = '/Users/samuelzhang/ttharden/fx_h2_k6/runs/wokwi'


def gen_of(pdir):
    """walk back through reservation rounds (_r<k>) to the generator's gen.json"""
    p = pdir
    for _ in range(6):
        g = os.path.join(p, 'gen.json')
        if os.path.exists(g):
            return p, json.load(open(g))
        pj = json.load(open(os.path.join(p, 'placement.json')))['meta']
        p = pj.get('from') or pj.get('partial_from')
        if not p: break
        p = p if os.path.isabs(p) else os.path.join(os.path.dirname(os.path.dirname(pdir)), p)
    return None, {}


out = {'baseline': {'tag': 'h2', 'run': H2RUN, 'metrics_json': H2RUN + '/final/metrics.json', **compare.H2M,
                    'area_classes': os.path.abspath(os.path.join(here, '..', 'baseline', 'h2_area_classes.json'))},
       'gate': 'stdcell < 45475.8; slew/cap/fanout <= 281/2/6; setup and hold >= 0 at all 9 corners; route DRC 0; '
               'antenna 0; every FIRM cell held (FIXED, same origin/orient) at every step; resized cells within reservations',
       'candidates': []}
for arg in sys.argv[2:]:
    tag, pdir = arg.split('=', 1)
    sp = os.path.join(pdir, 'firm_summary.json')
    if not os.path.exists(sp):
        out['candidates'].append({'tag': tag, 'placement': os.path.abspath(pdir), 'status': 'no FIRM summary'}); continue
    s = json.load(open(sp)); r = compare.row(s); r['tag'] = tag
    gdir, g = gen_of(pdir)
    probes = sorted(glob.glob(s['work'].replace('_firm', '_probe') + '*'))
    out['candidates'].append({
        'tag': tag, 'placement': os.path.abspath(pdir), 'generator_dir': os.path.abspath(gdir) if gdir else None,
        'generator_args': g.get('args'), 'hpwl_pins_um': g.get('hpwl_pins_um'), 'cells_moved': g.get('cells_moved_from_h2'),
        'nondp_moved': g.get('nondp_moved'), 'mean_disp_um': g.get('mean_disp_um'),
        'partial_firm': json.load(open(os.path.join(pdir, 'placement.json')))['meta'].get('partial_firm', False),
        'firm_run': s['work'], 'probe_runs': probes, 'summary': os.path.abspath(sp),
        'metrics': s.get('metrics'), 'row': r, 'pass': r['pass'], 'why': r['why']})
json.dump(out, open(sys.argv[1], 'w'), indent=1)
print(f"wrote {sys.argv[1]}: {len(out['candidates'])} candidates, pass: {[c['tag'] for c in out['candidates'] if c.get('pass')]}")
