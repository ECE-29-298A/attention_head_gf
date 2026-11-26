#!/usr/bin/env python3
"""Build a self-contained review page for one placement (tetrising) experiment.

Usage: review_artifact.py <spec.json> <out.html>

The spec names a baseline run and one or more experiment runs (LibreLane run roots, e.g.
/Users/samuelzhang/ttharden/mr3_b_m). For each run, the page draws the final placed DEF to
scale and tabulates final/metrics.json against the baseline. Cells are drawn from real
coordinates; LEF sizes come from the PDK. Nothing is estimated.
"""
import glob, hashlib, html, json, os, re, sys

LEF = ("/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/"
       "54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/"
       "gf180mcu_fd_sc_mcu7t5v0/lef/gf180mcu_fd_sc_mcu7t5v0.lef")
PFX = "gf180mcu_fd_sc_mcu7t5v0__"
REPAIR = re.compile(r"^(fanout|rebuffer|split|hold|wire|input|output|max_cap|max_length|load_slew)\d+")
CLOCK = re.compile(r"^(clkbuf_|clkload|clknet|delaybuf)")

CLASS_KEYS = [  # (metrics class, label)
    ("sequential_cell", "Flops"),
    ("multi_input_combinational_cell", "Logic gates"),
    ("inverter", "Inverters"),
    ("buffer", "Buffers (synthesis)"),
    ("timing_repair_buffer", "Repair buffers"),
    ("clock_buffer", "Clock buffers"),
    ("clock_inverter", "Clock inverters"),
    ("tap_cell", "Tap cells"),
    ("endcap_cell", "Endcaps"),
    ("tie_cell", "Tie cells"),
]


def lef_sizes(path):
    sizes, cur = {}, None
    for line in open(path):
        t = line.split()
        if not t:
            continue
        if t[0] == "MACRO":
            cur = t[1]
        elif t[0] == "SIZE" and cur:
            sizes[cur] = (float(t[1]), float(t[3]))
        elif t[0] == "END" and len(t) > 1 and t[1] == cur:
            cur = None
    return sizes


def parse_def(path):
    txt = open(path).read()
    unit = float(re.search(r"UNITS DISTANCE MICRONS (\d+)", txt).group(1))
    d = [float(v) / unit for v in re.search(
        r"DIEAREA \( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \)", txt).groups()]
    sec = txt[txt.index("\nCOMPONENTS"):txt.index("END COMPONENTS")]
    comps = []
    for st in sec.split(";")[1:]:
        m = re.search(r"-\s+(\S+)\s+(\S+).*?\+\s+(PLACED|FIXED)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\S+)",
                      st, re.S)
        if m:
            comps.append((m.group(1), m.group(2), m.group(3),
                          float(m.group(4)) / unit, float(m.group(5)) / unit, m.group(6)))
    return d, comps


def kind(name, master, status):
    short = master.replace(PFX, "")
    if short.startswith(("fill_", "fillcap", "decap")) or name.startswith("FILLER"):
        return None                                   # fill and decap are not drawn
    if short.startswith(("filltie", "endcap")):
        return "tap"
    if status == "FIXED":
        return "fix"                                  # custom-placed by the experiment
    if CLOCK.match(name):
        return "clk"
    if REPAIR.match(name):
        return "rep"
    if short.startswith("antenna"):
        return "ant"
    return "std"


def svg_die(die, comps, sizes, crop=None, titles=False):
    x0, y0, x1, y1 = crop or die
    w, h = x1 - x0, y1 - y0
    out = [f'<svg viewBox="{x0:.2f} {-(y1):.2f} {w:.2f} {h:.2f}" class="die" '
           f'preserveAspectRatio="xMidYMid meet" role="img">',
           f'<rect class="c-core" x="{die[0]:.2f}" y="{-die[3]:.2f}" '
           f'width="{die[2]-die[0]:.2f}" height="{die[3]-die[1]:.2f}"/>']
    order = {"tap": 0, "ant": 1, "std": 2, "rep": 3, "clk": 4, "fix": 5}
    items = []
    for name, master, status, x, y, _ in comps:
        k = kind(name, master, status)
        if k is None or master not in sizes:
            continue
        cw, ch = sizes[master]
        if crop and (x + cw < x0 or x > x1 or y + ch < y0 or y > y1):
            continue
        items.append((order[k], k, name, master, x, y, cw, ch))
    for _, k, name, master, x, y, cw, ch in sorted(items):
        r = (f'<rect class="c-{k}" x="{x:.2f}" y="{-(y+ch):.2f}" '
             f'width="{cw:.2f}" height="{ch:.2f}"')
        if titles:
            r += f'><title>{html.escape(name)} · {master.replace(PFX, "")}</title></rect>'
        else:
            r += "/>"
        out.append(r)
    out.append("</svg>")
    return "".join(out)


def counts(comps):
    c = {}
    for name, master, status, *_ in comps:
        k = kind(name, master, status)
        if k:
            c[k] = c.get(k, 0) + 1
    return c


def fixed_bbox(comps, sizes):
    xs = [(x, y, x + sizes[m][0], y + sizes[m][1]) for n, m, s, x, y, _ in comps
          if kind(n, m, s) == "fix" and m in sizes]
    if not xs:
        return None
    return (min(a[0] for a in xs), min(a[1] for a in xs),
            max(a[2] for a in xs), max(a[3] for a in xs))


def run_data(root, sizes):
    final = os.path.join(root, "runs", "wokwi", "final")
    mpath = os.path.join(final, "metrics.json")
    dpath = glob.glob(os.path.join(final, "def", "*.def"))[0]
    m = json.load(open(mpath))
    die, comps = parse_def(dpath)
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()[:12]
    return {"m": m, "die": die, "comps": comps, "mpath": mpath, "dpath": dpath,
            "msha": sha(mpath), "dsha": sha(dpath), "counts": counts(comps),
            "bbox": fixed_bbox(comps, sizes)}


def corner_min(m, prefix):
    v = [val for k, val in m.items() if k.startswith(prefix + "__corner") and val is not None]
    return min(v) if v else None


def antenna(m):
    for k in ("route__antenna_violation__count", "antenna__violating__nets"):
        if k in m:
            return m[k]
    return None


def fmt(v, nd=1):
    if v is None:
        return "–"
    if isinstance(v, (int,)) or (isinstance(v, float) and v.is_integer() and nd == 0):
        return f"{int(v):,}"
    return f"{v:,.{nd}f}"


def delta(v, b, nd=1, better="lower"):
    if v is None or b is None:
        return ""
    d = v - b
    if abs(d) < 10 ** (-nd) / 2:
        return '<span class="d d-0">±0</span>'
    good = d < 0 if better == "lower" else d > 0
    return f'<span class="d {"d-good" if good else "d-bad"}">{d:+,.{nd}f}</span>'


def main(spec_path, out_path):
    spec = json.load(open(spec_path))
    sizes = lef_sizes(LEF)
    base = run_data(spec["baseline"]["run"], sizes)
    runs = [(r, run_data(r["run"], sizes)) for r in spec["runs"]]
    cols = [(spec["baseline"]["label"], base, None)] + [(r["label"], d, r) for r, d in runs]
    E = html.escape

    def row(label, get, nd=1, better="lower", unit=""):
        b = get(base["m"])
        cells = [f'<td class="num">{fmt(b, nd)}</td>']
        for _, d, _r in cols[1:]:
            v = get(d["m"])
            cells.append(f'<td class="num">{fmt(v, nd)} {delta(v, b, nd, better)}</td>')
        return f'<tr><th scope="row">{E(label)}<span class="u">{unit}</span></th>{"".join(cells)}</tr>'

    head = "".join(f'<th scope="col">{E(l)}</th>' for l, _, _ in cols)
    area_rows = [row("Std-cell area", lambda m: m.get("design__instance__area__stdcell"), 1, "lower", " µm²")]
    for key, label in CLASS_KEYS:
        area_rows.append(row(label, lambda m, k=key: m.get(f"design__instance__area__class:{k}"), 1, "lower", " µm²"))
    area_rows.append(row("Wire length", lambda m: m.get("route__wirelength"), 0, "lower", " µm"))

    def legal_setup(m):
        return corner_min(m, "timing__setup__ws")

    sig_rows = [
        row("Setup WNS, worst corner", legal_setup, 2, "higher", " ns"),
        row("Hold WNS, worst corner", lambda m: corner_min(m, "timing__hold__ws"), 3, "higher", " ns"),
        row("Slew violations", lambda m: m.get("design__max_slew_violation__count"), 0),
        row("Cap violations", lambda m: m.get("design__max_cap_violation__count"), 0),
        row("Fanout violations", lambda m: m.get("design__max_fanout_violation__count"), 0),
        row("Power (vectorless)", lambda m: (m.get("power__total") or 0) * 1e3, 3, "lower", " mW"),
        row("Magic DRC errors", lambda m: m.get("magic__drc_error__count"), 0),
        row("LVS errors", lambda m: m.get("design__lvs_error__count"), 0),
        row("Antenna violations", antenna, 0),
    ]

    views = []
    for label, d, r in cols:
        c = d["counts"]
        bb = d["bbox"]
        meta = [f'{c.get("fix", 0)} fixed', f'{c.get("std", 0)} placed by tool',
                f'{c.get("rep", 0)} repair buffers', f'{c.get("clk", 0)} clock cells']
        note = f'<p class="note">{E(r["note"])}</p>' if r and r.get("note") else ""
        crop = ""
        if bb:
            m_ = 12.0
            cb = (max(d["die"][0], bb[0] - m_), max(d["die"][1], bb[1] - m_),
                  min(d["die"][2], bb[2] + m_), min(d["die"][3], bb[3] + m_))
            crop = (f'<figure class="crop"><figcaption>Close-up of the fixed cells: bounding box '
                    f'{bb[2]-bb[0]:.2f} × {bb[3]-bb[1]:.2f} µm at ({bb[0]:.2f}, {bb[1]:.2f}). '
                    f'Hover a cell for its instance and master.</figcaption>'
                    f'<div class="scroll">{svg_die(d["die"], d["comps"], sizes, cb, True)}</div></figure>')
        views.append(
            f'<section class="view"><h3>{E(label)}</h3>{note}'
            f'<p class="meta">{" · ".join(meta)}</p>'
            f'<div class="scroll">{svg_die(d["die"], d["comps"], sizes)}</div>{crop}'
            f'<p class="src">DEF <code>{E(d["dpath"])}</code> · sha256 {d["dsha"]}</p></section>')

    verif = "".join(f"<li>{E(v)}</li>" for v in spec.get("verification", []))
    evid = "".join(f"<li><code>{E(v)}</code></li>" for v in spec.get("evidence", []))
    srcs = "".join(f'<li>{E(l)}: <code>{E(d["mpath"])}</code> · sha256 {d["msha"]}</li>'
                   for l, d, _ in cols)
    dec = spec["decision"]
    die = base["die"]
    page = TEMPLATE.format(
        title=E(spec["title"]), module=E(spec["module"]), date=E(spec["date"]),
        commit=E(spec.get("commit", "")), kind=E(dec["kind"]), dlabel=E(dec["label"]),
        summary=E(spec["summary"]), dtext=E(dec["text"]), head=head,
        area="".join(area_rows), sig="".join(sig_rows), views="".join(views),
        verif=verif, evid=evid, srcs=srcs,
        diew=f"{die[2]-die[0]:.2f}", dieh=f"{die[3]-die[1]:.2f}")
    open(out_path, "w").write(page)
    print(out_path, f"{len(page)/1024:.0f} KiB")


TEMPLATE = """<title>{title}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Space+Grotesk:wght@500;600&display=swap">
<style>
/* Layout: one reading column; die views run full column width at true aspect ratio. */
:root {{
  --bg: #f6f7f9; --panel: #ffffff; --fg: #1b2330; --muted: #5d6878; --rule: #dde2ea;
  --fix: #1f5fd6; --std: #b9c2cf; --rep: #d9822b; --clk: #129488; --tap: #e6e9ee; --ant: #9aa4b2;
  --core: #eef1f5; --good: #1d7a46; --bad: #b3261e; --pill: #e8eefb;
  --display: "Space Grotesk", "Helvetica Neue", Arial, sans-serif;
  --body: "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #11151b; --panel: #171c24; --fg: #e3e8ef; --muted: #98a3b3; --rule: #2a313c;
  --fix: #6ea2ff; --std: #4a5464; --rep: #f0a050; --clk: #3cc4b6; --tap: #232a34; --ant: #5d6878;
  --core: #1b212a; --good: #5cc98a; --bad: #ff8a80; --pill: #1e2a40; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #11151b; --panel: #171c24; --fg: #e3e8ef; --muted: #98a3b3; --rule: #2a313c;
  --fix: #6ea2ff; --std: #4a5464; --rep: #f0a050; --clk: #3cc4b6; --tap: #232a34; --ant: #5d6878;
  --core: #1b212a; --good: #5cc98a; --bad: #ff8a80; --pill: #1e2a40; color-scheme: dark; }}
body {{ background: var(--bg); color: var(--fg); font: 15px/1.55 var(--body); }}
.wrap {{ max-width: 1100px; margin: 0 auto; padding-block: 28px 56px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 28px; }}
header {{ display: grid; gap: 8px; }}
.eyebrow {{ font: 500 12px/1 var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }}
h1 {{ font: 600 30px/1.15 var(--display); margin: 0; text-wrap: balance; }}
h2 {{ font: 600 19px/1.2 var(--display); margin: 0 0 10px; }}
h3 {{ font: 600 16px/1.2 var(--display); margin: 0; }}
p {{ margin: 0; max-width: 72ch; }}
.pill {{ justify-self: start; font: 500 13px/1 var(--body); padding: 6px 10px; border-radius: 999px; background: var(--pill); }}
.pill.rejected {{ color: var(--bad); }} .pill.adopted {{ color: var(--good); }} .pill.block {{ color: var(--fix); }}
.panel {{ background: var(--panel); border: 1px solid var(--rule); border-radius: 8px; padding: 18px; min-width: 0; }}
.scroll {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }}
th, td {{ padding: 6px 10px; border-bottom: 1px solid var(--rule); text-align: left; vertical-align: top; white-space: nowrap; }}
thead th {{ font: 500 12px/1.3 var(--body); color: var(--muted); }}
td.num {{ font: 13px/1.4 var(--mono); text-align: right; }}
th[scope=row] {{ font-weight: 500; }} .u {{ color: var(--muted); font-weight: 400; }}
.d {{ display: inline-block; min-width: 5.5em; font-size: 12px; }}
.d-good {{ color: var(--good); }} .d-bad {{ color: var(--bad); }} .d-0 {{ color: var(--muted); }}
.views {{ display: grid; gap: 22px; }}
.view {{ display: grid; gap: 8px; min-width: 0; }}
.meta, .src, .note, figcaption {{ color: var(--muted); font-size: 13px; }}
.src code {{ font: 12px var(--mono); word-break: break-all; }}
svg.die {{ width: 100%; height: auto; display: block; background: var(--panel); }}
.crop svg.die {{ max-height: 520px; }}
figure {{ margin: 0; display: grid; gap: 6px; }}
.c-core {{ fill: var(--core); }} .c-fix {{ fill: var(--fix); }} .c-std {{ fill: var(--std); }}
.c-rep {{ fill: var(--rep); }} .c-clk {{ fill: var(--clk); }} .c-tap {{ fill: var(--tap); }} .c-ant {{ fill: var(--ant); }}
.legend {{ display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; color: var(--muted); }}
.legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
.legend i {{ width: 12px; height: 12px; border-radius: 2px; display: inline-block; }}
ul {{ margin: 0; padding-left: 20px; display: grid; gap: 4px; }}
li code, p code {{ font: 12.5px var(--mono); word-break: break-all; }}
.two {{ display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
</style>
<div class="wrap">
<header>
  <div class="eyebrow">Tetris review · {module} · {date} · commit {commit}</div>
  <h1>{title}</h1>
  <div class="pill {kind}">{dlabel}</div>
  <p>{summary}</p>
</header>
<section class="panel"><h2>Decision</h2><p>{dtext}</p></section>
<section class="panel"><h2>Area by cell class</h2><div class="scroll"><table>
<thead><tr><th></th>{head}</tr></thead><tbody>{area}</tbody></table></div></section>
<section class="panel"><h2>Timing and signoff</h2><p class="meta">Under D6, timing only has to stay legal (WNS ≥ 0 at every corner).</p><div class="scroll"><table>
<thead><tr><th></th>{head}</tr></thead><tbody>{sig}</tbody></table></div></section>
<section class="panel"><h2>Placement</h2>
<p class="meta">Final placed DEF, drawn to scale on the {diew} × {dieh} µm die. Fill and decap cells are omitted.</p>
<div class="legend"><span><i class="lg" style="background:var(--fix)"></i>Fixed by the experiment</span>
<span><i style="background:var(--std)"></i>Placed by the tool</span><span><i style="background:var(--rep)"></i>Repair buffers</span>
<span><i style="background:var(--clk)"></i>Clock tree</span><span><i style="background:var(--tap);outline:1px solid var(--rule)"></i>Taps and endcaps</span></div>
<div class="views">{views}</div></section>
<div class="two">
<section class="panel"><h2>Verification</h2><ul>{verif}</ul></section>
<section class="panel"><h2>Evidence</h2><ul>{evid}</ul></section>
</div>
<section class="panel"><h2>Metric sources</h2><ul>{srcs}</ul></section>
</div>
"""

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
