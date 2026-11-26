#!/usr/bin/env python3
"""Build pd_flow/clusters/datapath/results.json from the screened runs (every number with the run it came from).
usage: make_results.py <config.json> <out results.json>
config: {"h2": [tag, ...], "x0": [tag, ...], "packing": [tag, ...], "winner": tag, "robust": [tag, ...],
         "signoff": {"tag": tag, "run": run_root} | null, "notes": {...}}
A tag names placements/<tag> (or its last reservation round placements/<tag>_r<k>), whose firm_summary.json
is the dryrun.py FIRM summary of that placement."""
import sys, os, json, glob, subprocess
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
ROOT = os.path.abspath(os.path.join(here, '..'))
H2RUN = '/Users/samuelzhang/ttharden/fx_h2_k6/runs/wokwi'
X0RUN = '/Users/samuelzhang/ttharden/md_x0_full/runs/wokwi'


def pdir_of(tag):
    c = sorted(glob.glob(os.path.join(ROOT, 'placements', tag + '_r*')))
    for p in reversed(c):
        if os.path.exists(os.path.join(p, 'firm_summary.json')): return p
    return os.path.join(ROOT, 'placements', tag)


def gen_of(pdir):
    p = pdir
    for _ in range(6):
        g = os.path.join(p, 'gen.json')
        if os.path.exists(g): return json.load(open(g))
        m = json.load(open(os.path.join(p, 'placement.json')))['meta']
        p = m.get('from') or m.get('partial_from')
        if not p: return {}
        if not os.path.isabs(p): p = os.path.join(ROOT, p)
        if not os.path.exists(os.path.join(p, 'placement.json')): return {}
    return {}


def rows(tags, ref):
    env = dict(os.environ, DP_REF=ref)
    code = ("import sys,json; sys.path.insert(0,%r); import compare\n"
            "out=[]\n"
            "for p in sys.argv[1:]:\n"
            "    s=json.load(open(p)); r=compare.row(s); r['summary']=p; r['firm_run']=s['work']\n"
            "    r['area_classes']={k:round(v['area'],3) for k,v in s.get('area_classes',{}).get('classes',{}).items()}\n"
            "    r['per_corner']=(s.get('metrics') or {}).get('per_corner'); r['all_held']=s.get('ALL_HELD')\n"
            "    r['reservation_misses']=s.get('reservation_misses'); r['resized']=len(s.get('resized_at_32',{}))\n"
            "    import dplib, footprint; D=dplib.Design() if 'D' not in dir() else D\n"
            "    Pl=dplib.Placement.load(D, s['placement_dir']); r['footprint_measured']=footprint.footprint(D, Pl, [n for n in D.dp if n in Pl.cells])\n"
            "    out.append(r)\n"
            "print(json.dumps({'ref': compare.H2M, 'ref_tag': compare.REFTAG, 'rows': out}))\n") % here
    paths, missing = [], []
    for t in tags:
        sp = os.path.join(pdir_of(t), 'firm_summary.json')
        (paths if os.path.exists(sp) else missing).append(sp if os.path.exists(sp) else t)
    r = subprocess.run([sys.executable, '-c', code] + paths, capture_output=True, text=True, env=env)
    if r.returncode: raise SystemExit(r.stderr)
    J = json.loads(r.stdout)
    for row, t in zip(J['rows'], [t for t in tags if t not in missing]):
        row['tag'] = t; pd = pdir_of(t); g = gen_of(pd)
        row['placement'] = pd; row['generator_args'] = g.get('args'); row['hpwl_pins_um'] = g.get('hpwl_pins_um')
        row['footprint'] = g.get('footprint'); row['cells_moved'] = g.get('cells_moved_from_h2'); row['nondp_moved'] = g.get('nondp_moved')
    J['missing'] = missing
    return J


cfg = json.load(open(sys.argv[1]))
out = {'objective': 'D10 area: design__instance__area__stdcell after signoff (dry run reproduces the harden)',
       'references': {'h2': {'run': H2RUN, 'metrics': H2RUN + '/final/metrics.json'},
                      'x0': {'run': X0RUN, 'metrics': X0RUN + '/final/metrics.json', 'shipping': True}},
       'gate': 'area < ref; slew/cap/fanout <= ref (x0 242/1/0); setup and hold >= 0 at all 9 corners; route DRC 0; '
               'antenna 0; every FIRM cell held at every step DEF (check_held); resized cells within their reservations',
       'notes': cfg.get('notes', {})}
out['h2_screens'] = rows(cfg.get('h2', []), H2RUN)
out['x0_screens'] = rows(cfg.get('x0', []), X0RUN)
pk = rows(cfg.get('packing', []), X0RUN)
out['packing_sequence'] = [{'tag': r['tag'], 'packing': r['footprint_measured']['packing'],
                            'region_um2': r['footprint_measured']['region_um2'],
                            'pack_w': (r.get('generator_args') or {}).get('pack_w'), 'area': r['area'], 'slew_cap_fanout': r['slew_cap_fo'],
                            'pass': r['pass'], 'firm_run': r['firm_run']} for r in pk['rows']]
out['packing_converged'] = cfg.get('packing_converged')
out['winner'] = cfg.get('winner'); out['robustness'] = cfg.get('robust')
out['signoff'] = cfg.get('signoff')
if cfg.get('signoff') and cfg['signoff'].get('run'):
    mp = os.path.join(cfg['signoff']['run'], 'final', 'metrics.json')
    if os.path.exists(mp):
        M = json.load(open(mp)); g = M.get
        out['signoff']['metrics'] = {
            'metrics_json': mp, 'stdcell_area': g('design__instance__area__stdcell'),
            'slew': g('design__max_slew_violation__count'), 'cap': g('design__max_cap_violation__count'),
            'fanout': g('design__max_fanout_violation__count'),
            'setup_ws_min': min(v for k, v in M.items() if k.startswith('timing__setup__ws__corner:')),
            'hold_ws_min': min(v for k, v in M.items() if k.startswith('timing__hold__ws__corner:')),
            'route_drc': g('route__drc_errors'), 'magic_drc': g('magic__drc_error__count'), 'klayout_drc': g('klayout__drc_error__count'),
            'lvs_errors': g('design__lvs_error__count'), 'antenna_nets': g('antenna__violating__nets'),
            'wirelength_um': g('route__wirelength'), 'power_total_W': g('power__total'),
            'instance_count': g('design__instance__count')}
json.dump(out, open(sys.argv[2], 'w'), indent=1)
print('wrote', sys.argv[2])
