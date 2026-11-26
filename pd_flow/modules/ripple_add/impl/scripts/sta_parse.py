#!/usr/bin/env python3
"""Parse sta_char.sh logs into OUTDIR/sta_summary.json.

Usage: sta_parse.py OUTDIR N
For every corner and section (LIBERTY_ONLY, SPEF, BLOCK_LIBERTY_MODEL) and arc (input, edge):
data arrival time at s[N-1] (= path delay, input delay 0) and the slew at s[N-1]. Also the
max-slew violator count at the 20 fF boundary, vectorless power, and the block Liberty pin caps.
"""
import json
import re
import sys
from pathlib import Path


def arcs(text, section):
    m = re.search(rf"=== {section}(.*?)(?:\n=== |\Z)", text, re.S)
    out = {}
    if not m:
        return out
    for blk in re.split(r"\nARC ", m.group(1))[1:]:
        head, body = blk.split("\n", 1)
        inp, edge = head.split()
        arr = re.search(r"([-0-9.]+)\s+data arrival time", body)
        # last line with the output port s[...] carries its slew in the first numeric column(s)
        sl = None
        for line in body.splitlines():
            if re.search(r"\ss\[\d+\] \(out\)", line):
                nums = re.findall(r"-?\d+\.\d+", line)
                if len(nums) >= 2:
                    sl = float(nums[-3]) if len(nums) >= 3 else float(nums[0])
        out[f"{inp}:{edge}"] = {"delay_ns": float(arr.group(1)) if arr else None, "slew_ns": sl}
    return out


def main():
    d, n = Path(sys.argv[1]), int(sys.argv[2])
    res = {"N": n, "boundary": {"input_transition_ns_liberty": 0.30, "output_load_pF": 0.020},
           "corners": {}}
    for c in ("tt_025C_3v30", "ss_125C_3v00", "ff_n40C_3v60"):
        t = (d / f"sta_{c}.log").read_text()
        mt = (d / f"model_{c}.log").read_text()
        r = {"liberty_only": arcs(t, "LIBERTY_ONLY"), "spef_nom": arcs(t, "SPEF"),
             "spef_nom_sensitized": arcs(t, "SENSITIZED"),
             "block_liberty_model": arcs(mt, "BLOCK_LIBERTY_MODEL")}
        ms = re.search(r"=== MAX_SLEW_CHECK.*?(?:max slew violation count|max_slew)\D*(\d+)?", t, re.S)
        vio = re.findall(r"\(VIOLATED\)", t.split("=== MAX_SLEW_CHECK")[1].split("=== POWER")[0])
        r["max_slew_cap_violations_at_20fF"] = len(vio)
        pw = re.search(r"^Total\s+([-0-9.eE+]+)\s+([-0-9.eE+]+)\s+([-0-9.eE+]+)\s+([-0-9.eE+]+)", t, re.M)
        if pw:
            r["vectorless_power_W"] = {"internal": float(pw.group(1)), "switching": float(pw.group(2)),
                                       "leakage": float(pw.group(3)), "total": float(pw.group(4))}
            r["vectorless_energy_per_100ns_op_pJ"] = round(float(pw.group(4)) * 100e-9 * 1e12, 4)
        lib = (d / f"ripple_add__{c}.lib").read_text()
        caps = {}
        for m in re.finditer(r"pin\(\"?([\w\[\]]+)\"?\)\s*\{(.*?)\n\s*\}", lib, re.S):
            cm = re.search(r"\bcapacitance\s*:\s*([0-9.eE+-]+)", m.group(2))
            if cm:
                caps[m.group(1)] = float(cm.group(1))
        bus = {}
        for m in re.finditer(r"bus\(\"?(\w+)\"?\)\s*\{(.*?)\n  \}", lib, re.S):
            for cm in re.finditer(r"capacitance\s*:\s*([0-9.eE+-]+)", m.group(2)):
                bus.setdefault(m.group(1), []).append(float(cm.group(1)))
        r["block_liberty_pin_cap_pF"] = {"pins": caps,
                                         "bus_min_max": {k: [min(v), max(v)] for k, v in bus.items()}}
        res["corners"][c] = r
    (d / "sta_summary.json").write_text(json.dumps(res, indent=1) + "\n")
    for c, r in res["corners"].items():
        print(c, "SPEF", {k: v["delay_ns"] for k, v in r["spef_nom"].items()})
        print(c, "LIB ", {k: v["delay_ns"] for k, v in r["liberty_only"].items()})
        print(c, "SENS", {k: (v["delay_ns"], v["slew_ns"]) for k, v in r["spef_nom_sensitized"].items()})
        print(c, "MODEL", {k: v["delay_ns"] for k, v in r["block_liberty_model"].items()})
        print(c, "slew/cap vio", r["max_slew_cap_violations_at_20fF"], "power", r.get("vectorless_power_W"))


if __name__ == "__main__":
    main()
