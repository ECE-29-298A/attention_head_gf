#!/usr/bin/env python3
"""Run a chain of LibreLane 3.0.14 steps standalone (Docker), re-using a finished run's per-step
config.json with overrides.  Nothing in the reference run is modified.
usage: step_chain.py <ref_run_dir> <out_dir> <start_state_in.json> <spec.json>
spec.json: [{"step": "OpenROAD.CutRows", "ref": "18-openroad-cutrows", "set": {VAR: VALUE}}, ...]"""
import sys, os, json, subprocess
ref, out, state, spec = sys.argv[1], sys.argv[2], sys.argv[3], json.load(open(sys.argv[4]))
os.makedirs(out, exist_ok=True)
here = os.path.dirname(os.path.abspath(__file__))
for i, s in enumerate(spec):
    cfg = json.load(open(os.path.join(ref, s['ref'], 'config.json')))
    cfg.update(s.get('set', {}))
    d = os.path.join(out, f"{i:02d}-{s['ref']}")
    cp = d + '.config.json'; json.dump(cfg, open(cp, 'w'), indent=1)
    r = subprocess.run([os.path.join(here, 'step_run.sh'), s['step'], cp, state, d], capture_output=True, text=True)
    print(r.stdout.strip()[-400:])
    if r.returncode: print(r.stderr[-2000:]); sys.exit(1)
    state = os.path.join(d, 'state_out.json')
print('FINAL_STATE', state)
