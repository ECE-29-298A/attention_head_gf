#!/usr/bin/env python3
"""View manifest (sha256) and cross-view consistency for the hardened block.

Usage: check_views.py N OUT.json
V1 pins: the same port set (a[0..N-1], b[..], cin, s[..], power VPWR/VGND where the view has power)
   and the same directions in LEF, GDS text labels, DEF, gate Verilog (nl/pnl), the layout-extracted
   Verilog, the behavioural model, the CDL, the PEX subckt, and every Liberty (flow final/lib x9 and
   n<N>/sta block models x3);
V2 size: LEF SIZE = DEF DIEAREA = GDS top-cell bounding box (KLayout) = check_block.json die;
V3 pin geometry: every LEF pin rectangle equals the DEF pin rectangle (same layer);
V4 delay: block Liberty (nom corners) worst cin/a[0]/b[0] -> s[N-1] vs OpenSTA+SPEF and vs SPICE (PEX),
   at the same boundary; reported as ratios, not judged here (the judgement is in IMPLEMENTATION.md).
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

IMPL = Path(__file__).resolve().parents[1]
KL = "/Applications/klayout.app/Contents/MacOS/klayout"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def bits(n):
    return ({f"a[{i}]" for i in range(n)} | {f"b[{i}]" for i in range(n)} | {"cin"},
            {f"s[{i}]" for i in range(n)})


def verilog_ports(text, n):
    ins, outs = set(), set()
    for d, w, names in re.findall(r"\b(input|output|inout)\s+(?:wire\s+)?(\[\d+:\d+\])?\s*([\w\s,]+?)\s*[;,)\n]", text):
        for nm in [x.strip() for x in names.split(",") if x.strip()]:
            if nm in ("wire",):
                continue
            ex = {f"{nm}[{i}]" for i in range(int(w[1:].split(":")[0]) + 1)} if w else {nm}
            (ins if d == "input" else outs if d == "output" else ins).update(ex)
    return ins, outs


def main():
    n, out = int(sys.argv[1]), Path(sys.argv[2])
    d = IMPL / f"n{n}"
    F = d / "run" / "final"
    I, O = bits(n)
    res = {"N": n, "views": {}, "checks": {}}
    files = {
        "gds": F / "gds/ripple_add.gds", "gds_klayout_stream": F / "klayout_gds/ripple_add.klayout.gds",
        "lef": F / "lef/ripple_add.lef", "def": F / "def/ripple_add.def",
        "verilog_gate_nl": F / "nl/ripple_add.nl.v", "verilog_gate_pnl": F / "pnl/ripple_add.pnl.v",
        "verilog_layout_extracted": IMPL / f"contract/ripple_add_n{n}_extracted.v",
        "verilog_behavioural": IMPL / f"views/ripple_add_n{n}_behav.v",
        "spice_cell_level_extracted": F / "spice/ripple_add.spice",
        "cdl_schematic": d / f"lvs/ripple_add_n{n}.cdl", "spice_schematic": d / f"lvs/ripple_add_n{n}.spice",
        "spice_pex_magic": d / f"pex/ripple_add_n{n}_pex.spice",
        "spef_nom": F / "spef/nom/ripple_add.nom.spef", "spef_min": F / "spef/min/ripple_add.min.spef",
        "spef_max": F / "spef/max/ripple_add.max.spef", "sdc": F / "sdc/ripple_add.sdc",
    }
    for p in sorted((F / "lib").glob("*/*.lib")):
        files[f"liberty_flow_{p.parent.name}"] = p
    for p in sorted((d / "sta").glob("ripple_add__*.lib")):
        files[f"liberty_block_model_{p.stem.split('__')[1]}"] = p
    for k, p in files.items():
        res["views"][k] = {"path": str(p.relative_to(IMPL)), "sha256": sha(p) if p.exists() else "MISSING",
                           "bytes": p.stat().st_size if p.exists() else 0}
    errs = {}

    def chk(view, ins, outs, pw=None):
        e = []
        if ins != I:
            e.append(f"inputs differ: {sorted(ins ^ I)[:6]}")
        if outs != O:
            e.append(f"outputs differ: {sorted(outs ^ O)[:6]}")
        if pw is not None and pw != {"VPWR", "VGND"}:
            e.append(f"power {sorted(pw)}")
        errs[view] = e

    # LEF
    lef = files["lef"].read_text()
    li, lo, lp, lrect = set(), set(), set(), {}
    for m in re.finditer(r"PIN (\S+)\n(.*?)END \1", lef, re.S):
        nm, body = m.group(1), m.group(2)
        use = re.search(r"USE (\w+)", body)
        dr = re.search(r"DIRECTION (\w+)", body).group(1)
        if use and use.group(1) in ("POWER", "GROUND"):
            lp.add(nm)
            continue
        (li if dr == "INPUT" else lo).add(nm)
        r = re.search(r"LAYER (\w+) ;\s*RECT ([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)", body)
        lrect[nm] = (r.group(1),) + tuple(round(float(x), 3) for x in r.groups()[1:])
    chk("lef", li, lo, lp)
    size = tuple(float(x) for x in re.search(r"SIZE ([\d.]+) BY ([\d.]+)", lef).groups())
    # DEF
    df = files["def"].read_text()
    dbu = int(re.search(r"UNITS DISTANCE MICRONS (\d+)", df).group(1))
    da = [int(x) / dbu for x in re.search(r"DIEAREA \( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \)", df).groups()]
    di, do, dp, drect = set(), set(), set(), {}
    pins = df.split("PINS")[1].split("END PINS")[0]
    for m in re.finditer(r"- (\S+) \+ NET \S+ \+ DIRECTION (\w+)(.*?);", pins, re.S):
        nm = m.group(1).replace("\\", "")
        if "USE POWER" in m.group(3) or "USE GROUND" in m.group(3):
            dp.add(nm)
            continue
        (di if m.group(2) == "INPUT" else do).add(nm)
        r = re.search(r"LAYER (\w+) \( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \).*?(?:PLACED|FIXED) \( (-?\d+) (-?\d+) \) (\w+)",
                      m.group(3), re.S)
        if r:
            lay = r.group(1)
            x1, y1, x2, y2, px, py = (int(v) for v in r.groups()[1:7])
            assert r.group(8) == "N", r.group(8)
            drect[nm] = (lay, round((px + x1) / dbu, 3), round((py + y1) / dbu, 3),
                         round((px + x2) / dbu, 3), round((py + y2) / dbu, 3))
    chk("def", di, do, dp or None)
    res["checks"]["V3_pin_rects_lef_eq_def"] = {
        "compared": len(lrect), "mismatch": {k: (lrect[k], drect.get(k)) for k in lrect if lrect[k] != drect.get(k)}}
    # GDS: labels and bbox via KLayout
    kscript = IMPL / "scripts" / "gds_info.py"
    kout = subprocess.run([KL, "-b", "-r", str(kscript), "-rd", f"gds={files['gds']}"], capture_output=True, text=True).stdout
    gi = json.loads(kout.strip().splitlines()[-1])
    glab = set(gi["labels"])
    errs["gds_labels"] = [] if glab == I | O | {"VPWR", "VGND"} else [f"labels differ: {sorted(glab ^ (I | O | {'VPWR', 'VGND'}))[:8]}"]
    # Verilog views
    for v in ("verilog_gate_nl", "verilog_layout_extracted", "verilog_behavioural"):
        chk(v, *verilog_ports(files[v].read_text(), n))
    pi, po = verilog_ports(files["verilog_gate_pnl"].read_text(), n)
    pw = {x for x in pi if x in ("VPWR", "VGND")}
    chk("verilog_gate_pnl", pi - pw, po, pw)
    # SPICE-family subckt ports (no directions)
    for v in ("cdl_schematic", "spice_cell_level_extracted", "spice_pex_magic"):
        t = files[v].read_text().replace("\n+", " ")
        m = re.search(r"^\.subckt ripple_add\S* ([^\n]*)", t, re.M | re.I)
        ps = {x.replace("\\", "") for x in m.group(1).split() if "=" not in x}
        e = [] if ps - {"VSUB"} == I | O | {"VPWR", "VGND"} else [f"ports differ: {sorted(ps ^ (I | O | {'VPWR', 'VGND'}))[:8]}"]
        errs[v] = e
    # Liberty
    lib_area = {}
    for k in [k for k in files if k.startswith("liberty")]:
        t = files[k].read_text()
        li2, lo2 = set(), set()
        # direction is an attribute of the pin/bus group header, before any nested group
        for m in re.finditer(r"\bpin\s*\(\s*\"?([\w\[\]]+)\"?\s*\)\s*\{([^{}]*)", t):
            dm = re.search(r"direction\s*:\s*(\w+)", m.group(2))
            if dm:
                (li2 if dm.group(1) == "input" else lo2).add(m.group(1))
        for m in re.finditer(r"\bbus\s*\(\s*\"?(\w+)\"?\s*\)\s*\{([^{}]*)", t):
            dm = re.search(r"direction\s*:\s*(\w+)", m.group(2))
            for i in range(n):
                (li2 if dm.group(1) == "input" else lo2).add(f"{m.group(1)}[{i}]")
        chk(k, li2, lo2)
        am = re.search(r"cell\s*\(\s*\"?ripple_add\"?\s*\)\s*\{.*?area\s*:\s*([\d.]+)", t, re.S)
        lib_area[k] = float(am.group(1)) if am else None
    res["checks"]["V1_pins"] = {"errors": {k: v for k, v in errs.items() if v}, "views_checked": sorted(errs)}
    cb = json.loads((d / "check_block.json").read_text()) if (d / "check_block.json").exists() else {}
    res["checks"]["V2_size"] = {"lef_size_um": size, "def_diearea_um": da, "gds_bbox_um": gi["bbox"],
                                "liberty_area_um2": lib_area,
                                "check_block_die": cb.get("checks", {}).get("P6_size", {}).get("die_um")}
    s_ok = (abs(size[0] - (da[2] - da[0])) < 1e-3 and abs(size[1] - (da[3] - da[1])) < 1e-3 and
            all(abs(a - b) < 1e-3 for a, b in zip(gi["bbox"], da)))
    res["checks"]["V2_size"]["pass"] = s_ok
    # V4 delay comparison (tt/ss/ff)
    sta = json.loads((d / "sta" / "sta_summary.json").read_text())
    v4 = {}
    for c, sc in (("tt_025C_3v30", "tt"), ("ss_125C_3v00", "ss"), ("ff_n40C_3v60", "ff")):
        r = sta["corners"][c]
        worst = lambda sec: max(v["delay_ns"] for v in r[sec].values())
        row = {"block_liberty_worst_ns": worst("block_liberty_model"),
               "sta_spef_worst_ns": worst("spef_nom"), "sta_spef_sensitized_worst_ns": worst("spef_nom_sensitized"),
               "liberty_only_worst_ns": worst("liberty_only")}
        sp = d / "spice" / f"{sc}_delay.json"
        if sp.exists():
            row["spice_pex_worst_ns"] = json.loads(sp.read_text())["worst"]["delay_ns"]
            row["ratio_spice_over_block_liberty"] = round(row["spice_pex_worst_ns"] / row["block_liberty_worst_ns"], 3)
            row["ratio_spice_over_sta_sensitized"] = round(row["spice_pex_worst_ns"] / row["sta_spef_sensitized_worst_ns"], 3)
        row["ratio_block_liberty_over_sta_spef"] = round(row["block_liberty_worst_ns"] / row["sta_spef_worst_ns"], 3)
        v4[sc] = row
    res["checks"]["V4_delay"] = v4
    res["all_structural_pass"] = (not res["checks"]["V1_pins"]["errors"] and s_ok and
                                  not res["checks"]["V3_pin_rects_lef_eq_def"]["mismatch"] and
                                  all(v["sha256"] != "MISSING" for v in res["views"].values()))
    out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res["checks"].items()}, indent=1)[:3000])
    print("STRUCTURAL_PASS" if res["all_structural_pass"] else "STRUCTURAL_FAIL")


if __name__ == "__main__":
    main()
