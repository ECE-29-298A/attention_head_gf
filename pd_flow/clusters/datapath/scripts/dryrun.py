#!/usr/bin/env python3
"""Gated dry run of the M-FIRM mechanism on standalone LibreLane steps, re-using h2's per-step
config.json of the reference run (env DP_REF, default h2; Architect B's pilot_dryrun.py, plus a machine-wide container gate and a summary).

  17 ManualMacroPlacement (MACRO_PLACEMENT_CFG -> FIRM) .. 28 GPL (ties only) .. 32 RepairDesignPostGPL
  [37: 34 DPL, 35 CTS, 37 ResizerTimingPostCTS] [44: 39 GRT .. 42 antenna repair, 44 DRT]
  [55: 45, 54 RCX, 55 STAPostPNR (9 corners)]

usage: dryrun.py <placement_dir> <work_dir> [--through 32|37|44|55] [--probe]
  --probe: Odb.ManualGlobalPlacement (PLACED, same positions) before step 32 so DPL can legalize the
           resizer's in-place upsizing; only used to learn the resizer's decisions for a placement.
Writes <work>/summary.json: resized custom cells, and for a FIRM run through 55 the signoff metrics,
area by class, held check over every step DEF and the reservation check.
"""
import sys, os, json, glob, argparse, subprocess, shutil, re, collections, time
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib
from dplib import read_def, sha

REF = dplib.REF   # reference run (h2 by default; env DP_REF selects another, e.g. x0)
ap = argparse.ArgumentParser(); ap.add_argument('pdir'); ap.add_argument('work')
ap.add_argument('--through', default='55'); ap.add_argument('--probe', action='store_true')
a = ap.parse_args()
assert a.work.startswith('/Users/samuelzhang/ttharden/'), 'work dir must be under the docker mount'
if os.path.exists(a.work): shutil.rmtree(a.work)
os.makedirs(a.work)
cfg = os.path.join(a.work, 'macro_placement.cfg'); shutil.copy(os.path.join(a.pdir, 'macro_placement.cfg'), cfg)
shutil.copy(os.path.join(a.pdir, 'placement.json'), os.path.join(a.work, 'placement.json'))
d = lambda pfx: os.path.basename(glob.glob(os.path.join(REF, pfx + '-*'))[0])
ids = [('17', 'Odb.ManualMacroPlacement'), ('18', 'OpenROAD.CutRows'), ('19', 'OpenROAD.TapEndcapInsertion'),
       ('20', 'Odb.AddPDNObstructions'), ('21', 'OpenROAD.GeneratePDN'), ('22', 'Odb.RemovePDNObstructions'),
       ('23', 'Odb.AddRoutingObstructions'), ('24', 'OpenROAD.GlobalPlacementSkipIO'), ('25', 'OpenROAD.IOPlacement'),
       ('26', 'Odb.CustomIOPlacement'), ('27', 'Odb.ApplyDEFTemplate'), ('28', 'OpenROAD.GlobalPlacement'),
       ('32', 'OpenROAD.RepairDesignPostGPL')]
if a.through in ('37', '44', '55'):
    ids += [('34', 'OpenROAD.DetailedPlacement'), ('35', 'OpenROAD.CTS'), ('37', 'OpenROAD.ResizerTimingPostCTS')]
if a.through in ('44', '55'):
    ids += [('39', 'OpenROAD.GlobalRouting'), ('40', 'OpenROAD.CheckAntennas'), ('41', 'Odb.DiodesOnPorts'),
            ('42', 'OpenROAD.RepairAntennas'), ('44', 'OpenROAD.DetailedRouting')]
if a.through == '55':
    ids += [('45', 'Odb.RemoveRoutingObstructions'), ('54', 'OpenROAD.RCX'), ('55', 'OpenROAD.STAPostPNR')]
spec = [{'step': sid, 'ref': d(n), **({'set': {'MACRO_PLACEMENT_CFG': cfg}} if n == '17' else {})} for n, sid in ids]
if a.probe:
    mgp = json.load(open(os.path.join(a.pdir, 'manual_global_placements.json')))
    k = [i for i, x in enumerate(spec) if x['step'] == 'OpenROAD.RepairDesignPostGPL'][0]
    spec.insert(k, {'step': 'Odb.ManualGlobalPlacement', 'ref': d('33'), 'set': {'MANUAL_GLOBAL_PLACEMENTS': mgp}})
json.dump(spec, open(os.path.join(a.work, 'spec.json'), 'w'), indent=1)
t0 = time.time()
state = os.path.join(REF, d('17'), 'state_in.json'); chain = os.path.join(a.work, 'chain'); os.makedirs(chain)
ok, failed = True, None
for i, s in enumerate(spec):
    c = json.load(open(os.path.join(REF, s['ref'], 'config.json'))); c.update(s.get('set', {}))
    od = os.path.join(chain, f"{i:02d}-{s['ref']}"); cp = od + '.config.json'; json.dump(c, open(cp, 'w'), indent=1)
    r = subprocess.run([os.path.join(here, 'step_run_gated.sh'), s['step'], cp, state, od], capture_output=True, text=True)
    if r.returncode:
        ok, failed = False, s['step']; print(r.stdout[-2500:]); break
    state = os.path.join(od, 'state_out.json')
P = json.load(open(os.path.join(a.pdir, 'placement.json')))['cells']
D = dplib.Design()
summ = {'placement_dir': os.path.abspath(a.pdir), 'placement_sha16': sha(os.path.join(a.pdir, 'placement.json')),
        'work': a.work, 'through': a.through, 'probe': a.probe, 'chain_ok': ok, 'failed_step': failed,
        'seconds': round(time.time() - t0, 1)}
s32 = glob.glob(os.path.join(chain, '*-32-*', '*.def'))
res = {}
if s32:
    F = read_def(s32[0])
    for n, p in P.items():
        c = F['comps'].get(n)
        if c and c['master'] != p['master']:
            res[n] = c['master']
summ['resized_at_32'] = res
summ['reservation_misses'] = {n: m for n, m in res.items() if D.wsites(m) > P[n]['w_res_sites']}


def held(defpath):
    """every custom cell FIXED, same origin and orientation; a resized cell must stay in its span."""
    F = read_def(defpath); bad = collections.Counter(); ex = []; resized = {}
    for n, p in P.items():
        c = F['comps'].get(n); why = None
        if c is None: why = 'missing'
        elif c['status'] != 'FIXED': why = 'status ' + str(c['status'])
        elif c['orient'] != p['orient']: why = 'orient'
        elif abs(c['y'] - p['y']) > 1e-3: why = 'moved'
        else:
            w0 = D.LEFS[p['master']][0]; w1 = D.LEFS[c['master']][0]
            mir = p['orient'] in dplib.MIRRORED
            # origin = left edge for N/FS, right edge for FN/S
            o0 = p['x'] + (w0 if mir else 0); o1 = c['x'] + (w1 if mir else 0)
            span0 = dplib.X0 + p['span_site'] * dplib.SITE; span1 = span0 + p['w_res_sites'] * dplib.SITE
            if abs(o0 - o1) > 1e-3: why = 'moved'
            elif c['master'] != p['master']:
                resized[n] = c['master']
                if c['x'] < span0 - 1e-3 or c['x'] + w1 > span1 + 1e-3: why = 'resized beyond reservation'
        if why:
            bad[why] += 1
            if len(ex) < 6: ex.append((n, why))
    return {'ok': not bad, 'violations': dict(bad), 'examples': ex, 'resized': len(resized)}


if not a.probe:
    hs = {}
    for dp_ in sorted(glob.glob(os.path.join(chain, '*', '*.def'))):
        hs[os.path.basename(os.path.dirname(dp_))] = held(dp_)
    summ['held'] = hs
    summ['ALL_HELD'] = bool(hs) and all(v['ok'] for v in hs.values())
last = glob.glob(os.path.join(chain, '*-55-*', 'state_out.json'))
if ok and last and not a.probe:
    M = json.load(open(last[0]))['metrics']; g = M.get
    corners = sorted({k.split('__corner:')[1] for k in M if '__corner:' in k})
    summ['metrics'] = {
        'stdcell_area': g('design__instance__area__stdcell'),
        'slew': g('design__max_slew_violation__count'), 'cap': g('design__max_cap_violation__count'),
        'fanout': g('design__max_fanout_violation__count'),
        'setup_ws_min': min(v for k, v in M.items() if k.startswith('timing__setup__ws__corner:')),
        'hold_ws_min': min(v for k, v in M.items() if k.startswith('timing__hold__ws__corner:')),
        'route_drc': g('route__drc_errors'), 'antenna_nets': g('antenna__violating__nets'),
        'antenna_pins': g('antenna__violating__pins'), 'route_antenna': g('route__antenna_violation__count'),
        'wirelength_um': g('route__wirelength'), 'grt_wirelength': g('global_route__wirelength'),
        'power_total_W': g('power__total'),
        'per_corner': {c: {'setup': g(f'timing__setup__ws__corner:{c}'), 'hold': g(f'timing__hold__ws__corner:{c}'),
                           'slew': g(f'design__max_slew_violation__count__corner:{c}'),
                           'cap': g(f'design__max_cap_violation__count__corner:{c}'),
                           'fanout': g(f'design__max_fanout_violation__count__corner:{c}')} for c in corners}}
    s44 = glob.glob(os.path.join(chain, '*-44-*', '*.def'))
    if s44:
        r = subprocess.run([sys.executable, os.path.join(here, 'area_classes.py'), s44[0], '--json', os.path.join(a.work, 'area_classes.json')],
                           capture_output=True, text=True)
        if r.returncode == 0:
            summ['area_classes'] = json.load(open(os.path.join(a.work, 'area_classes.json')))
        else:
            summ['area_classes_error'] = r.stderr[-800:]
json.dump(summ, open(os.path.join(a.work, 'summary.json'), 'w'), indent=1)
m = summ.get('metrics', {})
print(f"DRYRUN {'OK' if ok else 'FAILED at ' + str(failed)} {a.work} {summ['seconds']} s | resized {len(res)} "
      f"misses {len(summ['reservation_misses'])} | held {summ.get('ALL_HELD')} | area {m.get('stdcell_area')} "
      f"slew/cap/fo {m.get('slew')}/{m.get('cap')}/{m.get('fanout')} setup {m.get('setup_ws_min')} hold {m.get('hold_ws_min')} "
      f"drc {m.get('route_drc')} ant {m.get('antenna_nets')} wire {m.get('wirelength_um')}")
sys.exit(0 if ok else 1)
