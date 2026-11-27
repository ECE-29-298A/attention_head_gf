#!/usr/bin/env python3
"""Screen CTS outcomes of candidate placements with the real tool: each candidate = gen_tetris.py args;
generate placements/<tag>, then dryrun.py --mode r32 --through 35 (steps 33'(FIRM) 34 DPL 35 CTS of the
reference flow) in /Users/samuelzhang/ttharden/wc_work/<tag>_cts; collect the CTS census.
usage: cts_screen.py <spec.json> [--jobs 2]     spec: {"<tag>": ["--seed-def", "...", "--relocate", "c:x:y", ...], ...}
Writes logs/cts_screen_<spec basename>.json and prints one line per tag."""
import sys, os, json, subprocess, argparse, concurrent.futures as cf
here = os.path.dirname(os.path.abspath(__file__)); root = os.path.dirname(here)
ap = argparse.ArgumentParser(); ap.add_argument('spec'); ap.add_argument('--jobs', type=int, default=2); ap.add_argument('--through', default='35')
a = ap.parse_args()
S = json.load(open(a.spec))


def one(tag):
    pd = os.path.join(root, 'placements', tag)
    r = subprocess.run([sys.executable, os.path.join(here, 'gen_tetris.py'), '--out', pd] + S[tag], capture_output=True, text=True, cwd=root)
    open(os.path.join(root, 'logs', f'gen_{tag}.log'), 'w').write(r.stdout + r.stderr)
    if r.returncode: return tag, {'error': 'gen failed', 'tail': (r.stdout + r.stderr)[-400:]}
    w = f'/Users/samuelzhang/ttharden/wc_work/{tag}_cts' if a.through == '35' else f'/Users/samuelzhang/ttharden/wc_work/{tag}_r32'
    r = subprocess.run([sys.executable, os.path.join(here, 'dryrun.py'), pd, w, '--mode', 'r32', '--through', a.through], capture_output=True, text=True)
    open(os.path.join(root, 'logs', f'{tag}_cts.log'), 'w').write(r.stdout + r.stderr)
    s = json.load(open(os.path.join(w, 'summary.json')))
    c = s.get('cts', {})
    out = {'cts_area': c.get('cts_area'), 'leaves': c.get('n_leaves'), 'dummies': c.get('dummies'), 'masters': c.get('masters'),
           'held': s.get('ALL_HELD'), 'work': w, 'fanouts': sorted(l['ff'] for l in c.get('leaves', []))}
    if 'metrics' in s:
        m = s['metrics']; out.update({k: m[k] for k in ('stdcell_area', 'slew', 'cap', 'fanout', 'setup_ws_min', 'hold_ws_min', 'route_drc', 'antenna_nets', 'wirelength_um')})
    return tag, out


res = {}
with cf.ThreadPoolExecutor(a.jobs) as ex:
    for tag, o in ex.map(one, list(S)):
        res[tag] = o; print(tag, json.dumps(o), flush=True)
json.dump(res, open(os.path.join(root, 'logs', 'cts_screen_' + os.path.basename(a.spec)), 'w'), indent=1)
