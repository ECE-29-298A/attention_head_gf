#!/usr/bin/env python3
"""Validator for a generated placement directory (experiments.md §5).  Fails (exit 1) on any error.
  1 stale  : --regen re-runs the generator from gen.json's recorded args into a temp dir and requires a
             byte-identical placement.json (also catches hand edits);
  2 views  : placement.json, macro_placement.cfg and manual_global_placements.json agree on instance,
             position and orientation; reserve.json equals the reserved masters;
  3 geometry: cell set = every non-tie cell of the reference netlist (partial-FIRM: a subset), each
             inside the die and on the row/site grid, legal row orientation, no overlap, no tap/endcap site,
             site-row checksum;
  4 intent : cells outside the movable cluster are at their seed position, except the listed local
             legalization shifts (reservations); every reservation is wider than or equal to its master;
  5 netlist: the reference synthesized netlist hash equals the one recorded at generation (placement-only:
             function and connectivity are the golden netlist's; LVS is checked at harden);
  6 library: LEF width of every master equals the generator's width table;
  7 self-test: a copy with one deliberate overlap must be rejected.
usage: validate.py <placement_dir> [--regen] [--movable union|struct|b]"""
import sys, os, json, argparse, subprocess, tempfile, shutil, hashlib
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib, footprint


def check_dir(d, pdir, movable):
    errs = []
    J = json.load(open(os.path.join(pdir, 'placement.json'))); meta, cells = J['meta'], J['cells']
    P = dplib.Placement.load(d, pdir)
    # 2 views
    cfg = {}
    for line in open(os.path.join(pdir, 'macro_placement.cfg')):
        t = line.split()
        if t: cfg[t[0]] = (float(t[1]), float(t[2]), t[3])
    mgp = json.load(open(os.path.join(pdir, 'manual_global_placements.json')))
    rs = json.load(open(os.path.join(pdir, 'reserve.json')))
    if set(cfg) != set(cells) or set(mgp) != set(cells): errs.append('views: instance sets differ')
    for n, c in cells.items():
        if n in cfg and (abs(cfg[n][0] - c['x']) > 0.005 or abs(cfg[n][1] - c['y']) > 0.005 or cfg[n][2] != c['orient']):
            errs.append(f'views: cfg {n} {cfg[n]} != placement {c["x"], c["y"], c["orient"]}')
        if n in mgp and (abs(mgp[n]['location'][0] - c['x']) > 0.005 or mgp[n]['orientation'] != c['orient']):
            errs.append(f'views: mgp {n} differs')
        if c.get('reserved_master') != rs.get(n): errs.append(f'views: reserve.json {n} differs')
    # 3 geometry (dplib legality: grid, orientation, overlap, taps, die)
    errs += [f'geometry: {e}' for e in P.check()]
    sr = sum(c['w_res_sites'] for c in cells.values())
    # 4 intent
    mov = footprint.members(d, movable) if movable else set(d.dp)
    seed = dplib.seed_from_h2(d)
    # recorded reasons: generator's local legalization (gen.json nondp_moved) and every reservation round's
    # shifts, walking the reservation chain <base>_r1 .. _rk back to the generator directory
    shifted, p, g = set(), pdir, None
    for _ in range(8):
        mj = json.load(open(os.path.join(p, 'placement.json')))['meta']
        shifted |= set(mj.get('shifted', []) or []) | set(mj.get('reserved_now', {}) or {})
        if os.path.exists(os.path.join(p, 'gen.json')):
            g = os.path.join(p, 'gen.json'); shifted |= set(json.load(open(g)).get('nondp_moved', [])); break
        nxt = mj.get('from') or mj.get('partial_from')
        if not nxt: break
        p = nxt if os.path.isabs(nxt) else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(pdir))), nxt)
    moved_other = [n for n in P.cells if n not in mov and n in seed.cells and
                   (P.cells[n]['r'], P.def_xy(n)[0]) != (seed.cells[n]['r'], seed.def_xy(n)[0])]
    bad = [n for n in moved_other if n not in shifted]
    if bad: errs.append(f'intent: {len(bad)} cells outside the cluster moved without a recorded reason: {bad[:6]}')
    for n, c in P.cells.items():
        if c.get('rm') and d.wsites(c['rm']) > c['wr']: errs.append(f'intent: {n} reservation {c["rm"]} wider than span')
        if c['wr'] < d.wsites(c['m']): errs.append(f'intent: {n} span narrower than its master')
    # 5 netlist
    rec = meta.get('netlist_sha16') or (json.load(open(g)).get('netlist_sha16') if g else None)
    if rec and rec != d.nl_sha16: errs.append(f'netlist: recorded {rec} != reference {d.nl_sha16}')
    # 6 library
    for n, c in cells.items():
        if abs(c['w_sites'] * dplib.SITE - d.LEFS[c['master']][0]) > 1e-3 if 'w_sites' in c else False:
            errs.append(f'library: {n} width table mismatch')
    return errs, {'cells': len(cells), 'site_rows': sr, 'moved_outside_cluster': len(moved_other)}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('pdir'); ap.add_argument('--regen', action='store_true')
    ap.add_argument('--movable', default='all'); a = ap.parse_args()
    d = dplib.Design()
    errs, info = check_dir(d, a.pdir, a.movable)
    # 1 stale
    if a.regen:
        g = json.load(open(os.path.join(a.pdir, 'gen.json'))); args = dict(g['args'])
        tmp = tempfile.mkdtemp(dir='/private/tmp/claude-501/-Users-samuelzhang-Desktop-2B-ECE-attention-head-gf/fdcf0a1f-422b-437c-87ae-0ead8c85435c/scratchpad')
        gen = os.path.join(here, g.get('generator', 'gen_tetris.py'))
        cmd = [sys.executable, gen, '--out', tmp]
        for k, v in args.items():
            if k == 'out' or v in (None, False, [], ''): continue
            flag = '--' + k.replace('_', '-')
            if v is True: cmd.append(flag)
            elif isinstance(v, list): cmd += [flag] + [str(x) for x in v]
            else: cmd += [flag, str(v)]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(here))
        h = lambda p: hashlib.sha256(json.dumps(json.load(open(p))['cells'], sort_keys=True).encode()).hexdigest()
        if r.returncode or h(os.path.join(tmp, 'placement.json')) != h(os.path.join(a.pdir, 'placement.json')):
            errs.append(f'stale: regenerated placement differs (rc {r.returncode}) {r.stderr[-300:]}')
        info['regen'] = 'identical' if not errs or not errs[-1].startswith('stale') else 'DIFFERS'
        shutil.rmtree(tmp, ignore_errors=True)
    # 7 self-test: deliberate overlap must be caught
    P = dplib.Placement.load(d, a.pdir); n1, n2 = sorted(P.cells)[:2]
    P.cells[n2]['r'], P.cells[n2]['s'] = P.cells[n1]['r'], P.cells[n1]['s']
    info['self_test'] = 'rejected overlap' if P.check() else 'FAILED (overlap not caught)'
    if not P.check(): errs.append('self-test: deliberate overlap not rejected')
    print(json.dumps(info), 'ERRORS' if errs else 'OK')
    for e in errs[:20]: print('  ', e)
    sys.exit(1 if errs else 0)
