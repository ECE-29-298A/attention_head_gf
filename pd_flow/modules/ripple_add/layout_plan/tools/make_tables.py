#!/usr/bin/env python3
"""Generate the PLAN.md result tables from the raw run outputs (never transcribed by hand):
module level from explore/sta/*.log and explore/activity.json; chip level from
chip_runs/logs/llsynth_*.txt and chip_runs/<tag>/harden/metrics.json. Writes tables.md."""
import glob, json, os, re
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
out = []
# ---------------- module level
act = json.load(open(os.path.join(HERE, "explore/activity.json")))
sta = {}
for f in glob.glob(os.path.join(HERE, "explore/sta/*.log")):
    t = open(f).read()
    m = re.search(r"^RESULT (\S+) (\S+) worst_arrival_ns=([0-9.]+)", t, re.M)
    p = re.search(r"^Total\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", t, re.M)
    sta[(m.group(1), m.group(2))] = (float(m.group(3)), [float(x) for x in p.groups()])
names = {"abc": "ABC-mapped (module, default ABC)", "addf1": "pure addf_1 chain", "addf1x3": "hybrid: addf_1 + xor3_1 MSB",
         "addf2x3": "addf_2 chain + xor3_1 MSB", "alt12x3": "addf_1/addf_2 alternating + xor3_1 MSB"}
for n in (22, 12):
    out.append(f"\n**Module level, N={n}** (OpenSTA 0.30 ns input slew, 0.02 pF output load, no wire; power: input activity 0.5/cycle at 10 MHz, TT; switched pin C: {act['abc_n22']['vectors']} random vectors)\n")
    out.append("| Implementation | Cells | Area µm² | Worst a/b/cin→s TT ns | SS ns | Power TT µW (total) | Switched pin C fF/vector zero-delay | unit-delay |")
    out.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for k in ("abc", "addf1", "addf1x3", "addf2x3", "alt12x3"):
        a = act[f"{k}_n{n}"]; tt = sta[(f"{k}_n{n}", "tt_025C_3v30")]; ss = sta[(f"{k}_n{n}", "ss_125C_3v00")]
        out.append(f"| {names[k]} | {a['cells']} | {a['area_um2']:.2f} | {tt[0]:.3f} | {ss[0]:.3f} | {tt[1][3]*1e6:.1f} | "
                   f"{a['switched_pin_cap_fF_per_vector_zero_delay']:.1f} | {a['switched_pin_cap_fF_per_vector_unit_delay']:.1f} |")
# ---------------- chip level
syn = {}
for f in glob.glob(os.path.join(HERE, "chip_runs/logs/llsynth_*.txt")):
    t = open(f).read().split()
    syn[t[0].replace("ra_", "")] = (float(t[1]), int(t[2]))
order = [("base", "golden RTL, ABC in context (re-run)"), ("n03", "golden, XOR operands swapped (noise)"),
         ("n04", "golden, OR operands swapped (noise)"), ("abcfrozen", "module ABC netlists frozen as cells"),
         ("addf1", "pure addf_1 chains (22 + 12)"), ("hyb", "hybrid addf_1 + xor3_1, both widths, carry on xor3 A3"),
         ("hybcos", "determinism check: bit-identical to hyb"), ("hyb22", "hybrid on N=22 only, N=12 ABC, carry on A3"),
         ("final", "superseded generator RTL, carry on xor3 A1 (slow arc), free placement"),
         ("final_mgp", "final (A1) + MANUAL_GLOBAL_PLACEMENTS: REJECTED, drift"), ("final_fixed", "final (A1) + MACRO_PLACEMENT_CFG (FIRM)"),
         ("fixed_a3", "CURRENT generator RTL (carry on A3, RIPPLE_ADD_CELLS) + MACRO_PLACEMENT_CFG (FIRM)")]
out.append("\n**Chip level** (shipped flow: `ll_synth.sh` synthesis; full `tt_tool.py --harden`; power = LibreLane vectorless STA, nom TT)\n")
hdr = ["Variant", "Synth µm²", "Cells", "Std-cell µm²", "Util %", "Repair buf µm²", "Setup WNS ss/tt/ff ns",
       "Hold WNS ss/tt/ff ns", "Slew/Cap/Fanout", "Power mW (int/sw)", "Wire µm", "DRC/LVS"]
out.append("| " + " | ".join(hdr) + " |"); out.append("|" + "---|" * len(hdr))
for tag, desc in order:
    p = os.path.join(HERE, "chip_runs", tag, "harden", "metrics.json")
    s = syn.get(tag) or syn.get("final" if tag.startswith("final_") else tag)   # same RTL as 'final'
    hs = os.path.join(HERE, "chip_runs", tag, "harden", "synth_stat.json")
    if s is None and os.path.exists(hs):   # harden's own Yosys step (e.g. needs VERILOG_DEFINES)
        d = json.load(open(hs)); top = d.get("design") or next(iter(d["modules"].values()))
        s = (float(top["area"]), int(top["num_cells"]))
    if not os.path.exists(p):
        out.append(f"| {tag}: {desc} | {s[0]:.1f} | {s[1]} | not run |" if s else f"| {tag} | not run |"); continue
    m = json.load(open(p))
    g = lambda k: m.get(k)
    sw = lambda c: g(f"timing__setup__ws__corner:max_{c}")
    hw = lambda c: g(f"timing__hold__ws__corner:max_{c}") if c != "ff_n40C_3v60" else g("timing__hold__ws")
    out.append(f"| {tag}: {desc} | {s[0]:.1f} | {s[1]} | {g('design__instance__area__stdcell'):.1f} | "
               f"{g('design__instance__utilization')*100:.2f} | {g('design__instance__area__class:timing_repair_buffer'):.1f} | "
               f"{sw('ss_125C_3v00'):.2f} / {sw('tt_025C_3v30'):.2f} / {sw('ff_n40C_3v60'):.2f} | "
               f"{hw('ss_125C_3v00'):.3f} / {hw('tt_025C_3v30'):.3f} / {hw('ff_n40C_3v60'):.3f} | "
               f"{g('design__max_slew_violation__count')}/{g('design__max_cap_violation__count')}/{g('design__max_fanout_violation__count')} | "
               f"{g('power__total')*1e3:.3f} ({g('power__internal__total')*1e3:.3f}/{g('power__switching__total')*1e3:.3f}) | "
               f"{g('route__wirelength')} | {g('route__drc_errors')}+{g('magic__drc_error__count')}/{g('design__lvs_error__count')} |")
open(os.path.join(HERE, "tables.md"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
