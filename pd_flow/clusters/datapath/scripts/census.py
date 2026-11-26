#!/usr/bin/env python3
"""Routing-resource census (method step 3, routing-closure §1) from the tech LEF and the cell LEF,
for the masters the dp cluster uses, plus the flow's routing window.  Prints (and --json writes):
  - per routing layer: direction, pitch, offset, width, spacing, min area, shortest legal wire;
  - per master: layers carrying pin or OBS shapes (a master with no shape on a layer leaves that layer
    free for through-tracks), signal pins, Metal2 tracks crossing each signal pin's Metal1 shapes (cell origins
    sit on the Metal2 grid because the site width equals the Metal2 pitch);
  - rows: height / Metal3 pitch, so whether mirrored rows see the same horizontal track set;
  - routing window and scarce direction.
usage: census.py [--json OUT]"""
import sys, os, re, json, collections, argparse
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib
TLEF = '/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/techlef/gf180mcu_fd_sc_mcu7t5v0__nom.tlef'


def tech_layers():
    out = {}; cur = None; typ = None
    for line in open(TLEF):
        t = line.split('#')[0].split()
        if not t: continue
        if t[0] == 'LAYER' and len(t) == 2: cur, typ = t[1], None; continue
        if cur is None: continue
        if t[0] == 'END' and len(t) > 1 and t[1] == cur:
            if typ == 'ROUTING': out[cur] = L
            cur = None; continue
        if t[0] == 'TYPE':
            typ = t[1]; L = {'spacing': []}
        elif typ == 'ROUTING':
            if t[0] in ('DIRECTION',): L['direction'] = t[1]
            elif t[0] in ('PITCH', 'OFFSET', 'WIDTH', 'AREA'): L[t[0].lower()] = float(t[1])
            elif t[0] == 'SPACING' and len(t) >= 2:
                try: L['spacing'].append(float(t[1]))
                except ValueError: pass
    for L in out.values():
        L['min_spacing'] = min(L['spacing']) if L['spacing'] else None; del L['spacing']
        L['shortest_legal_wire'] = round(L['area'] / L['width'], 3) if L.get('area') and L.get('width') else None
    return out


def cell_shapes(masters):
    """{master: {'size', 'pins': {pin: {'use', 'rects': [(layer, x0, y0, x1, y1)]}}, 'obs_layers'}}"""
    out = {}; cur = pin = layer = None; sec = None
    for line in open(dplib.LEF):
        t = line.split()
        if not t: continue
        if t[0] == 'MACRO':
            cur = t[1].replace(dplib.PFX, ''); out[cur] = {'pins': {}, 'obs_layers': set()}; sec = None; continue
        if cur is None: continue
        if t[0] == 'SIZE': out[cur]['size'] = (float(t[1]), float(t[3]))
        elif t[0] == 'PIN': pin = t[1]; out[cur]['pins'][pin] = {'use': 'SIGNAL', 'rects': []}; sec = 'pin'
        elif t[0] == 'USE' and sec == 'pin': out[cur]['pins'][pin]['use'] = t[1]
        elif t[0] == 'OBS': sec = 'obs'
        elif t[0] == 'LAYER': layer = t[1]
        elif t[0] == 'RECT':
            v = [float(z) for z in t[1:5]]
            if sec == 'pin': out[cur]['pins'][pin]['rects'].append((layer, *v))
            elif sec == 'obs': out[cur]['obs_layers'].add(layer)
        elif t[0] == 'END' and len(t) > 1:
            if t[1] == pin: sec = None
            elif t[1] == cur or t[1] == dplib.PFX + cur: cur = None
    return {m: v for m, v in out.items() if m in masters}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--json'); a = ap.parse_args()
    d = dplib.Design(); TL = tech_layers()
    import json as _j
    cfg = _j.load(open(dplib.REF + '/39-openroad-globalrouting/config.json'))
    window = (cfg['RT_MIN_LAYER'], cfg['RT_MAX_LAYER']); adj = cfg.get('GRT_LAYER_ADJUSTMENTS')
    print('routing layers (nom tech LEF):')
    for n, L in TL.items(): print(f"  {n:7s} {L.get('direction','?'):10s} pitch {L.get('pitch')} offset {L.get('offset')} width {L.get('width')} "
                                  f"spacing {L.get('min_spacing')} area {L.get('area')} shortest wire {L.get('shortest_legal_wire')}")
    order = list(TL)
    win = order[order.index(window[0]):order.index(window[1]) + 1]
    dirs = collections.Counter(TL[l]['direction'] for l in win)
    print(f"routing window {window[0]}..{window[1]} = {win}; GRT layer adjustments {adj}; per direction {dict(dirs)}")
    dpm = collections.Counter(d.master[n] for n in d.dp)
    S = cell_shapes(set(dpm))
    m2 = TL['Metal2']; tbl = {}
    for m, v in sorted(S.items(), key=lambda kv: -dpm[kv[0]]):
        layers = sorted({r[0] for p in v['pins'].values() for r in p['rects']} | v['obs_layers'])
        reach = {}
        for pn, p in v['pins'].items():
            if p['use'] in ('POWER', 'GROUND'): continue
            xs = set()
            for (ly, x0, y0, x1, y1) in p['rects']:
                if ly != 'Metal1': continue
                k0 = int((x0 - m2['offset']) // m2['pitch']); k1 = int((x1 - m2['offset']) // m2['pitch']) + 1
                for k in range(k0, k1 + 1):
                    x = m2['offset'] + k * m2['pitch']       # cell origins sit on the Metal2 grid (site 0.56 = pitch)
                    if x0 - 1e-6 <= x <= x1 + 1e-6: xs.add(round(x, 3))
            reach[pn] = len(xs)
        tbl[m] = {'count_in_dp': dpm[m], 'width_sites': d.wsites(m), 'layers_with_shapes': layers,
                  'metal2_free_over_cell': 'Metal2' not in layers, 'metal2_tracks_per_pin': reach}
    print(f"masters in dp: {len(tbl)}; with any Metal2 shape: {[m for m, t in tbl.items() if not t['metal2_free_over_cell']]}")
    lowp = sorted(((min(t['metal2_tracks_per_pin'].values()) if t['metal2_tracks_per_pin'] else 0, m) for m, t in tbl.items()))
    print('fewest reachable Metal2 tracks per pin (master: min over its pins):', lowp[:10])
    rows_tracks = dplib.ROWH / TL['Metal3']['pitch']
    print(f"row height {dplib.ROWH} um = {rows_tracks:.2f} Metal3 tracks (whole number -> mirrored rows see the same track set: {abs(rows_tracks - round(rows_tracks)) < 1e-6})")
    out = {'tech_lef': TLEF, 'cell_lef': dplib.LEF, 'layers': TL, 'routing_window': win, 'per_direction': dict(dirs),
           'grt_layer_adjustments': adj, 'masters': tbl, 'row_tracks_metal3': rows_tracks,
           'scarce_direction': 'HORIZONTAL' if dirs.get('HORIZONTAL', 0) < dirs.get('VERTICAL', 0) else 'VERTICAL'}
    print('scarce direction (fewer layers in the window):', out['scarce_direction'])
    if a.json: json.dump(out, open(a.json, 'w'), indent=1)
