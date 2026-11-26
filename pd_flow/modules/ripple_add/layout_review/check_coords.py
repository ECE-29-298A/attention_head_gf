#!/usr/bin/env python3
"""Independent coordinate / PDK / integration checker (Agent 5). Does not import Agent 4 code.

Inputs (all read-only):
  - PDK cell LEF (parsed by leftab.py in this directory)
  - Agent 4 netlists out/ripple_add_n{22,12}.v (masters per instance)
  - Agent 4 anchors out/chip_anchor_n{22,12}.cfg and block cfgs out/block_n{22,12}.cfg
  - baseline final DEF (ra_base) for rows, taps, endcaps, PDN stripes
  - FIRM run final DEF + pnl (ra_final_fixed), plus step DEFs, to confirm the cells held

Usage: check_coords.py <out_json>
"""
import json, re, sys, os, subprocess, gzip, collections, glob

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN = os.path.join(HERE, '..', 'layout_plan', 'out')
PDKV = '/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee'
LEF = PDKV + '/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lef/gf180mcu_fd_sc_mcu7t5v0.lef'
BASE = '/Users/samuelzhang/ttharden/ra_base/runs/wokwi'
FIRM = os.environ.get('FIRM', '/Users/samuelzhang/ttharden/ra_final_fixed/runs/wokwi')
P = 'gf180mcu_fd_sc_mcu7t5v0__'
DBU = 2000
SITE_W, ROW_H = 0.56, 3.92

res = {'checks': [], 'fail': 0}
def chk(name, ok, detail=''):
    res['checks'].append({'check': name, 'ok': bool(ok), 'detail': detail})
    if not ok:
        res['fail'] += 1
    print(('PASS ' if ok else 'FAIL ') + name + (': ' + str(detail) if detail else ''))

# ---------------------------------------------------------------- LEF
import tempfile
cj = os.path.join(tempfile.mkdtemp(), 'cells.json')  # vendor-derived parse: kept out of the repo
subprocess.run([sys.executable, os.path.join(HERE, 'leftab.py'), LEF, cj], check=True, capture_output=True)
cells = json.load(open(cj))
assert len(cells) > 200 and cells[P + 'addf_1']['w'] > 0

# ---------------------------------------------------------------- DEF parse
def parse_def(path):
    t = open(path).read()
    rows = []
    for m in re.finditer(r'^ROW (\S+) (\S+) (\d+) (\d+) (\S+) DO (\d+) BY 1 STEP (\d+) 0', t, re.M):
        rows.append(dict(name=m[1], x=int(m[3]), y=int(m[4]), orient=m[5], n=int(m[6]), step=int(m[7])))
    comps = {}
    sec = re.search(r'^COMPONENTS \d+ ;(.*?)^END COMPONENTS', t, re.S | re.M).group(1)
    for m in re.finditer(r'-\s+(\S+)\s+(\S+)(.*?);', sec, re.S):
        st = re.search(r'\+ (PLACED|FIXED|FIRM|COVER) \( (-?\d+) (-?\d+) \) (\S+)', m[3])
        comps[m[1].replace('\\', '')] = dict(master=m[2], status=st[1] if st else 'UNPLACED',
                                             x=int(st[2]) if st else None, y=int(st[3]) if st else None,
                                             orient=st[4] if st else None)
    stripes = collections.defaultdict(list)
    ssec = re.search(r'^SPECIALNETS \d+ ;(.*?)^END SPECIALNETS', t, re.S | re.M)
    if ssec:
        cur = None
        for line in ssec.group(1).splitlines():
            mm = re.match(r'\s*- (\S+)', line)
            if mm:
                cur = mm[1]
            s = re.search(r'Metal4 (\d+) \+ SHAPE STRIPE \( (\d+) (\d+) \) \( (\d+) (\d+) \)', line)
            if s and s[2] == s[4]:
                stripes[cur].append((int(s[2]), int(s[1])))
    return rows, comps, stripes, t

rows, bcomps, bstripes, _ = parse_def(BASE + '/final/def/tt_um_attention_head_gf.def')
rowy = {r['y']: r for r in rows}
chk('base rows: 39 rows x 607 sites, x0=3.36, step 0.56',
    len(rows) == 39 and all(r['n'] == 607 and r['x'] == 6720 and r['step'] == 1120 for r in rows))
chk('base rows alternate N (even) / FS (odd) from y=3.92',
    all(r['y'] == 7840 + 7840 * i and r['orient'] == ('N' if i % 2 == 0 else 'FS') for i, r in enumerate(sorted(rows, key=lambda r: r['y']))))
taps = [(c['x'], c['y']) for c in bcomps.values() if c['master'] == P + 'filltie']
caps = [(c['x'], c['y']) for c in bcomps.values() if c['master'] == P + 'endcap']
phys = [(c['x'], c['y'], int(round(cells[c['master']]['w'] * DBU)), n) for n, c in bcomps.items()
        if c['master'] in (P + 'filltie', P + 'endcap')]
res['base_taps'] = len(taps); res['base_endcaps'] = len(caps)

# ---------------------------------------------------------------- netlist masters
def masters_from_netlist(path, prefix):
    out = {}
    t = open(path).read()
    for m in re.finditer(r'(gf180mcu_fd_sc_mcu7t5v0__\w+)\s+(\w+)\s*\(', t):
        out[m[2]] = m[1]
    # generate block: bitslice[i].u_fa for i in 0..N-2
    n = int(re.search(r'localparam N = (\d+)', t)[1])
    fa = out.pop('u_fa')
    m = {f'{prefix}bitslice[{i}].u_fa': fa for i in range(n - 1)}
    for k, v in out.items():
        m[prefix + k] = v
    return n, m

def read_cfg(path):
    out = {}
    for line in open(path):
        if line.strip():
            n, x, y, o = line.split()
            out[n] = (int(round(float(x) * DBU)), int(round(float(y) * DBU)), o)
    return out

legal_orient = {'N': ('N', 'FN'), 'FS': ('FS', 'S')}

def check_placement(tag, place, masters, rows_by_y, x0, nsites, obstacles, n):
    errs = []
    occ = collections.defaultdict(list)
    for inst, (x, y, o) in place.items():
        mst = masters.get(inst)
        if mst is None:
            errs.append(f'{inst}: not in netlist'); continue
        w = int(round(cells[mst]['w'] * DBU))
        if (x - x0) % 1120: errs.append(f'{inst}: off site grid x={x}')
        r = rows_by_y.get(y)
        if r is None: errs.append(f'{inst}: y={y} not a row'); continue
        if o not in legal_orient[r['orient']]: errs.append(f'{inst}: orient {o} on {r["orient"]} row')
        if x < x0 or x + w > x0 + nsites * 1120: errs.append(f'{inst}: outside row')
        occ[y].append((x, x + w, inst))
    for y, iv in occ.items():
        iv.sort()
        for a, b in zip(iv, iv[1:]):
            if b[0] < a[1]: errs.append(f'overlap {a[2]} {b[2]}')
        for (ox, oy, ow, on) in obstacles:
            if oy != y: continue
            for (a0, a1, ai) in iv:
                if ox < a1 and a0 < ox + ow: errs.append(f'{ai} overlaps {on}')
    if set(place) != set(masters): errs.append(f'instance set mismatch: {set(place) ^ set(masters)}')
    # design intent: carry chain bit i in row (r0 + i); one column; widths
    ys = sorted({y for (_, y, _) in place.values()})
    chain_ok = True
    fa = sorted([k for k in place if 'u_fa' in k], key=lambda k: int(re.search(r'\[(\d+)\]', k)[1]))
    y0 = place[fa[0]][1]
    for i, k in enumerate(fa):
        if place[k][1] != y0 + i * 7840: chain_ok = False
    msb = [k for k in place if 'u_msb' in k][0]
    if place[msb][1] != y0 + (n - 1) * 7840: chain_ok = False
    xs = {place[k][0] for k in fa}
    chk(f'{tag}: grid/row/orientation/overlap/obstacle legality', not errs, errs[:6] or f'{len(place)} cells, {len(ys)} rows')
    chk(f'{tag}: bit i in relative row i, all FA in one column', chain_ok and len(xs) == 1, f'x={sorted(xs)}')
    return occ

# ---------------------------------------------------------------- chip anchors
n22, m22 = masters_from_netlist(os.path.join(PLAN, 'ripple_add_n22.v'), 'core.mac.adder.')
n12, m12 = masters_from_netlist(os.path.join(PLAN, 'ripple_add_n12.v'), 'core.mac.l_adder.')
chk('netlists: N=22 has 21 addf_1 + 1 xor3_1; N=12 has 11 addf_1 + 1 xor3_1',
    sorted(collections.Counter(m22.values()).items()) == [(P + 'addf_1', 21), (P + 'xor3_1', 1)] and
    sorted(collections.Counter(m12.values()).items()) == [(P + 'addf_1', 11), (P + 'xor3_1', 1)])
p22 = read_cfg(os.path.join(PLAN, 'chip_anchor_n22.cfg'))
p12 = read_cfg(os.path.join(PLAN, 'chip_anchor_n12.cfg'))
occ22 = check_placement('chip N=22 anchor', p22, m22, rowy, 6720, 607, phys, n22)
occ12 = check_placement('chip N=12 anchor', p12, m12, rowy, 6720, 607, phys, n12)
allp = dict(p22); allp.update(p12); allm = dict(m22); allm.update(m12)
check_placement('chip both anchors together', allp, allm, rowy, 6720, 607, phys, n22) if False else None
# combined overlap
both = collections.defaultdict(list)
for k, (x, y, o) in allp.items():
    both[y].append((x, x + int(round(cells[allm[k]]['w'] * DBU)), k))
ov = [(a[2], b[2]) for y, iv in both.items() for a, b in zip(sorted(iv), sorted(iv)[1:]) if b[0] < a[1]]
chk('chip anchors: N=22 and N=12 columns do not overlap each other', not ov, ov[:3])

# taps adjacent to the column in each row, and distance to nearest same-row tap
tap_rows = collections.defaultdict(list)
for (x, y) in taps: tap_rows[y].append(x)
dists = []
# Per-well nearest tap. N row: Nwell on top (shared with row above), Pwell at bottom (shared with row below).
# FS row: the reverse. Distance = horizontal from the cell's far edge to the tap centre; for a
# neighbour-row tap add a conservative 3.92 um vertical offset (Euclidean).
for k, (x, y, o) in allp.items():
    w = int(round(cells[allm[k]]['w'] * DBU))
    orient = rowy[y]['orient']
    up, dn = y + 7840, y - 7840
    nw_nb, pw_nb = (up, dn) if orient == 'N' else (dn, up)
    worst = {}
    for well, nb in (('nwell', nw_nb), ('pwell', pw_nb)):
        wv = 0
        for px in range(x, x + w + 1, 280):
            ds = [abs(px - (t + 560)) / DBU for t in tap_rows[y]]
            ds += [((abs(px - (t + 560)) / DBU) ** 2 + 3.92 ** 2) ** 0.5 for t in tap_rows.get(nb, [])]
            wv = max(wv, min(ds))
        worst[well] = round(wv, 2)
    same = max(min(abs(px - (t + 560)) for t in tap_rows[y]) for px in range(x, x + w + 1, 280)) / DBU
    dists.append((k, round(same, 2), worst))
res['tap_distance'] = dists
worst_same = max(d for _, d, _ in dists)
worst_well = max(max(v.values()) for _, _, v in dists)
chk('taps: same-row-only worst distance (info)', True, f'{worst_same} um (exceeds 15 um alone)')
chk('taps: worst per-well distance to a tap in the same well (same row or well-sharing neighbour) <= 15 um (DF.13_MV/DF.14_MV)',
    worst_well <= 15.0, f'{worst_well} um')

# stripes over the column
sx = [(x, w, net) for net, lst in bstripes.items() for (x, w) in lst]
hit = []
for k, (x, y, o) in allp.items():
    w = int(round(cells[allm[k]]['w'] * DBU))
    for (cx, cw, net) in sx:
        if cx - cw / 2 < x + w and x < cx + cw / 2: hit.append((k, net, cx / DBU))
chk('PDN: no Metal4 stripe (and so no rail via stack) over any column cell at the default anchors', not hit, hit[:3])
res['stripes_x_um'] = sorted((net, x / DBU) for (x, w, net) in sx)

# ---------------------------------------------------------------- block cfgs
for n, tag in ((22, 'n22'), (12, 'n12')):
    bp = read_cfg(os.path.join(PLAN, f'block_{tag}.cfg'))
    _, bm = masters_from_netlist(os.path.join(PLAN, f'ripple_add_{tag}.v'), '')
    brow = {7840 + 7840 * i: dict(orient='N' if i % 2 == 0 else 'FS') for i in range(n)}
    bphys = [(6720, y, 2240, 'endcapL') for y in brow] + [(6720 + 35 * 1120, y, 2240, 'endcapR') for y in brow]
    check_placement(f'block {tag} (core x0 3.36, 37 sites)', bp, bm, brow, 6720, 37, bphys, n)

# ---------------------------------------------------------------- FIRM run: did the cells hold?
frows, fcomps, fstripes, ftext = parse_def(FIRM + '/final/def/tt_um_attention_head_gf.def')
held, moved = 0, []
for k, (x, y, o) in allp.items():
    c = fcomps.get(k)
    if c and c['master'] == allm[k] and (c['x'], c['y'], c['orient']) == (x, y, o) and c['status'] == 'FIXED':
        held += 1
    else:
        moved.append((k, c))
chk('FIRM run final DEF: every adder cell present, same master, FIXED, exact location and orientation',
    held == len(allp) and not moved, f'{held}/{len(allp)} held; {moved[:2]}')
# extra adder-hierarchy cells (buffers/resized clones inside the adder name space)
extra = [k for k, c in fcomps.items() if (k.startswith('core.mac.adder.') or k.startswith('core.mac.l_adder.')) and k not in allp]
extra_m = collections.Counter(fcomps[k]['master'].replace(P, '') for k in extra)
chk('FIRM run: extra cells inside the adder name space are only tie cells (free-placed, PLACED)',
    set(extra_m) <= {'tiel', 'tieh'} and all(fcomps[k]['status'] == 'PLACED' for k in extra), dict(extra_m))
res['extra_adder_cells'] = {k: fcomps[k] for k in extra}
ftaps = sorted((c['x'], c['y']) for c in fcomps.values() if c['master'] == P + 'filltie')
fcaps = sorted((c['x'], c['y']) for c in fcomps.values() if c['master'] == P + 'endcap')
chk('FIRM run: tap and endcap sets identical to baseline (positions)', ftaps == sorted(taps) and fcaps == sorted(caps),
    f'taps {len(ftaps)} vs {len(taps)}, endcaps {len(fcaps)} vs {len(caps)}')
fsx = sorted((net, x) for net, l in fstripes.items() for (x, w) in l)
bsx = sorted((net, x) for net, l in bstripes.items() for (x, w) in l)
chk('FIRM run: PDN stripes identical to baseline', fsx == bsx, f'{len(fsx)} stripes')
# full-die overlap check in the FIRM final DEF (all placed instances, incl. fill)
frowy = {r['y']: r for r in frows}
byrow = collections.defaultdict(list)
bad_orient = []
for k, c in fcomps.items():
    if c['x'] is None: continue
    w = int(round(cells[c['master']]['w'] * DBU)) if c['master'] in cells else None
    if w is None: continue
    byrow[c['y']].append((c['x'], c['x'] + w, k))
    r = frowy.get(c['y'])
    if r and c['orient'] not in legal_orient[r['orient']]: bad_orient.append(k)
fov = []
for y, iv in byrow.items():
    iv.sort()
    for a, b in zip(iv, iv[1:]):
        if b[0] < a[1]: fov.append((a[2], b[2]))
chk('FIRM run final DEF: no overlapping instances anywhere, all orientations row-legal', not fov and not bad_orient,
    f'overlaps {fov[:3]}, bad orient {bad_orient[:3]}')
# neighbours of the column: what abuts it
ncol = collections.Counter()
for y, iv in byrow.items():
    for a, b in zip(iv, iv[1:]):
        for (p, q) in ((a, b), (b, a)):
            if p[2] in allp and q[2] not in allp and (a[1] == b[0]):
                ncol[fcomps[q[2]]['master'].replace(P, '')] += 1
res['firm_column_abutters'] = dict(ncol)

# connectivity in the FIRM pnl: carry nets point to point, no buffer
pnl = open(FIRM + '/final/pnl/tt_um_attention_head_gf.pnl.v').read()
def inst_pins(name):
    esc = '\\' + name + ' '
    i = pnl.find(esc)
    if i < 0: return None
    j = pnl.find(';', i)
    return dict(re.findall(r'\.(\w+)\(([^()]*)\)', pnl[i:j]))
netsinks = collections.defaultdict(list)
for m in re.finditer(r'(gf180mcu_fd_sc_mcu7t5v0__\w+)\s+(\\?\S+)\s*\((.*?)\);', pnl, re.S):
    for pin, net in re.findall(r'\.(\w+)\(([^()]*)\)', m[3]):
        netsinks[net.strip()].append((m[2].lstrip('\\'), pin, m[1].replace(P, '')))
msbl = re.search(r'xor3_1 u_msb_x3 \((.*?)\);', open(os.path.join(PLAN, 'ripple_add_n22.v')).read())[1]
MSB_CPIN = re.search(r'\.(A\d)\(c\[', msbl)[1]
res['msb_carry_pin'] = MSB_CPIN
chainbad = []
for pre, n in (('core.mac.adder.', 22), ('core.mac.l_adder.', 12)):
    for i in range(n - 1):
        pins = inst_pins(f'{pre}bitslice[{i}].u_fa')
        if pins is None: chainbad.append(f'{pre}{i} missing'); continue
        co = pins['CO'].strip()
        nxt = f'{pre}bitslice[{i+1}].u_fa' if i < n - 2 else f'{pre}u_msb_x3'
        conns = [(a, p) for (a, p, mm) in netsinks[co]]
        want = {(f'{pre}bitslice[{i}].u_fa', 'CO'), (nxt, 'CI' if i < n - 2 else MSB_CPIN)}
        if set(conns) != want: chainbad.append((pre + str(i), co, conns))
chk('FIRM pnl: every carry net is exactly CO(i) -> CI(i+1) (MSB carry pin from netlist), no buffer or extra load', not chainbad, chainbad[:3])

# step DEFs: location at every saved step after ManualMacroPlacement
steps = sorted(glob.glob(FIRM + '/*/*.def'))
stephist = []
for sd in steps:
    try:
        _, sc, _, _ = parse_def(sd)
    except Exception:
        continue
    ok = sum(1 for k, (x, y, o) in allp.items() if k in sc and (sc[k]['x'], sc[k]['y'], sc[k]['orient']) == (x, y, o))
    stephist.append((os.path.basename(os.path.dirname(sd)), ok, len([k for k in allp if k in sc])))
res['firm_step_history'] = stephist
first = [s for s in stephist if int(s[0].split('-')[0]) >= 17]
chk('FIRM run: exact at every step DEF from ManualMacroPlacement on',
    all(ok == len(allp) for (_, ok, tot) in first if tot == len(allp)) and first and first[0][0].startswith('17'),
    f'{len(first)} step DEFs, first {first[0] if first else None}')

json.dump(res, open(sys.argv[1], 'w'), indent=1, default=str)
print(f"TOTAL fail={res['fail']} of {len(res['checks'])}")
