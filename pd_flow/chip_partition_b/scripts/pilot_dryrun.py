#!/usr/bin/env python3
"""Dry run of the FIRM custom-placement mechanism on standalone LibreLane steps (no harden):
17 ManualMacroPlacement (MACRO_PLACEMENT_CFG, FIRM) -> 18 CutRows -> 19 Tap/Endcap -> 20..28
(PDN, IO, GPL for the other cells) -> 32 RepairDesignPostGPL [-> 34 DPL -> 35 CTS -> 37 post-CTS
timing].  Re-uses the reference run's per-step config.json; writes only under <work>.
usage: pilot_dryrun.py <placement_dir> <work_dir> [--through 32|37|44|55] [--probe] [--ref RUN]
(44 adds GRT, antenna repair and DRT; 55 adds RCX and multi-corner STAPostPNR, i.e. the D2 slew/cap/fanout counts)
Prints the custom cells whose master the resizer changed (the next reservation)."""
import sys, os, json, glob, argparse, subprocess, shutil
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(here, '..', 'tools'))
from pdlib import read_def, lef_sizes
ap = argparse.ArgumentParser(); ap.add_argument('pdir'); ap.add_argument('work')
ap.add_argument('--through', default='32'); ap.add_argument('--probe', action='store_true', help='insert ManualGlobalPlacement (PLACED, same positions) before step 32 so DPL can legalize upsizing: only to learn the resizer decisions'); ap.add_argument('--ref', default='/Users/samuelzhang/ttharden/fx_h2_k6/runs/wokwi')
a = ap.parse_args()
if os.path.exists(a.work): shutil.rmtree(a.work)
os.makedirs(a.work)
cfg = os.path.join(a.work, 'macro_placement.cfg'); shutil.copy(os.path.join(a.pdir, 'macro_placement.cfg'), cfg)
d = lambda pfx: os.path.basename(glob.glob(os.path.join(a.ref, pfx + '-*'))[0])
ids = [('17', 'Odb.ManualMacroPlacement'), ('18', 'OpenROAD.CutRows'), ('19', 'OpenROAD.TapEndcapInsertion'),
       ('20', 'Odb.AddPDNObstructions'), ('21', 'OpenROAD.GeneratePDN'), ('22', 'Odb.RemovePDNObstructions'),
       ('23', 'Odb.AddRoutingObstructions'), ('24', 'OpenROAD.GlobalPlacementSkipIO'), ('25', 'OpenROAD.IOPlacement'),
       ('26', 'Odb.CustomIOPlacement'), ('27', 'Odb.ApplyDEFTemplate'), ('28', 'OpenROAD.GlobalPlacement'),
       ('32', 'OpenROAD.RepairDesignPostGPL')]
if a.through in ('37', '44', '55'): ids += [('34', 'OpenROAD.DetailedPlacement'), ('35', 'OpenROAD.CTS'), ('37', 'OpenROAD.ResizerTimingPostCTS')]
if a.through in ('44', '55'): ids += [('39', 'OpenROAD.GlobalRouting'), ('40', 'OpenROAD.CheckAntennas'), ('41', 'Odb.DiodesOnPorts'),
                              ('42', 'OpenROAD.RepairAntennas'), ('44', 'OpenROAD.DetailedRouting')]
if a.through == '55': ids += [('45', 'Odb.RemoveRoutingObstructions'), ('54', 'OpenROAD.RCX'), ('55', 'OpenROAD.STAPostPNR')]
spec = [{'step': sid, 'ref': d(n), **({'set': {'MACRO_PLACEMENT_CFG': cfg}} if n == '17' else {})} for n, sid in ids]
if a.probe:
    mgp = json.load(open(os.path.join(a.pdir, 'manual_global_placements.json'))) if os.path.exists(os.path.join(a.pdir, 'manual_global_placements.json')) else \
          {n: {'location': [c['x'], c['y']], 'orientation': c['orient']} for n, c in json.load(open(os.path.join(a.pdir, 'placement.json')))['cells'].items()}
    k = [i for i, x in enumerate(spec) if x['step'] == 'OpenROAD.RepairDesignPostGPL'][0]
    spec.insert(k, {'step': 'Odb.ManualGlobalPlacement', 'ref': d('33'), 'set': {'MANUAL_GLOBAL_PLACEMENTS': mgp}})
sp = os.path.join(a.work, 'spec.json'); json.dump(spec, open(sp, 'w'), indent=1)
r = subprocess.run([sys.executable, os.path.join(here, 'step_chain.py'), a.ref, os.path.join(a.work, 'chain'),
                    os.path.join(a.ref, d('17'), 'state_in.json'), sp], capture_output=True, text=True)
print(r.stdout[-1500:]); ok = r.returncode == 0
P = json.load(open(os.path.join(a.pdir, 'placement.json')))['cells']; L = lef_sizes()
s32 = glob.glob(os.path.join(a.work, 'chain', '*-32-*', '*.def'))
res = {}
if s32:
    F = read_def(s32[0])
    for n, p in P.items():
        c = F['comps'].get(n)
        if c and c['master'] != p['master']: res[n] = c['master']
else:
    log = glob.glob(os.path.join(a.work, 'chain', '*-32-*.log'))
    print('step 32 produced no DEF;', 'log ' + log[0] if log else '')
    if log:   # resizer decisions are logged before DPL: recover them from the failing run's ODB is not possible, so report the log tail
        print(open(log[0]).read()[-1500:])
json.dump(res, open(os.path.join(a.work, 'resized_custom.json'), 'w'), indent=1)
print('CHAIN', 'OK' if ok else 'FAILED', '| custom cells resized at step 32:', json.dumps(res))
sys.exit(0 if ok else 1)
