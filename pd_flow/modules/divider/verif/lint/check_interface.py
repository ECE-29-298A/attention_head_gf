#!/usr/bin/env python3
"""Check a Yosys write_json netlist of divider against the interface and structure contract.

Usage: check_interface.py <design.json> [--params LD CI]
--params (RTL mode): the top module must have exactly the parameters LATCH_DENOMINATOR = LD and
     CHECK_INVALID = CI (Yosys parameter_default_values; run_all.sh uses it on the chparam'd
     design and, without chparam, with 1 1 to enforce the DEFAULTS of R14).
The JSON is written after `proc -noopt; flatten; check -assert; scc; opt_clean` (the
configuration already fixed: chparam for RTL, the netlist as is for gate level).
R14 (interface): ports exactly clk, rst_n, start (in, 1), sum_in (in, 20), denominator
     (in, 12), shift (in, 1), busy, done (out, 1), result (out, 12). No other port.
R15 (structure): every state element is a positive-edge D flop without asynchronous
     reset/set ($dff, $dffe, $_DFF_P_, $_DFFE_PP_/PN_; the synchronous reset is logic in front
     of D), clocked by the clk port; no latches, memories or $anyinit; no `init` attribute on
     any wire; no black-box (non-primitive) cells after flatten. The NUMBER of flop bits is an
     implementation choice: it is reported (flop_bits=) but not constrained.
"""
import json
import sys

ALLOWED = ("$dff", "$dffe", "$_DFF_P_", "$_DFFE_PP_", "$_DFFE_PN_")
STATE_PREFIXES = ("$ff", "$dff", "$adff", "$sdff", "$aldff", "$dlatch", "$adlatch", "$sr",
                  "$mem", "$anyinit", "$_FF_", "$_DFF", "$_SDFF", "$_DLATCH", "$_SR", "$_ALDFF")


def main() -> int:
    d = json.load(open(sys.argv[1]))
    mods = d["modules"]
    tops = [m for m, x in mods.items() if x.get("attributes", {}).get("top")]
    errors = []
    if len(tops) != 1:
        errors.append(f"expected one top module, got {tops}")
    top = tops[0] if tops else next(iter(mods))
    md = mods[top]
    ports = {p: (x["direction"], len(x["bits"])) for p, x in md["ports"].items()}
    want = {"clk": ("input", 1), "rst_n": ("input", 1), "start": ("input", 1),
            "sum_in": ("input", 20), "denominator": ("input", 12), "shift": ("input", 1),
            "busy": ("output", 1), "done": ("output", 1), "result": ("output", 12)}
    if ports != want:
        errors.append(f"ports {ports} != expected {want}")
    clkbits = md["ports"].get("clk", {}).get("bits", [])
    nbits = 0
    for m, x in mods.items():
        for c, cd in x["cells"].items():
            t = cd["type"]
            if not t.startswith("$"):
                errors.append(f"unflattened / black-box cell {m}.{c} ({t})")
            elif t.startswith(STATE_PREFIXES):
                if t not in ALLOWED:
                    errors.append(f"state cell {c} of type {t} (async reset, latch, memory, negedge or init)")
                    continue
                p = cd.get("parameters", {})
                if t in ("$dff", "$dffe") and int(p.get("CLK_POLARITY", "1"), 2) != 1:
                    errors.append(f"flop {c} is negative-edge")
                ck = cd["connections"].get("CLK", cd["connections"].get("C"))
                if ck != clkbits:
                    errors.append(f"flop {c} clock {ck} is not the clk port {clkbits}")
                nbits += int(p.get("WIDTH", "1"), 2) if t in ("$dff", "$dffe") else 1
        for n, nd in x["netnames"].items():
            if "init" in nd.get("attributes", {}):
                errors.append(f"wire {m}.{n} has an init (power-up) value")
    if "--params" in sys.argv:
        i = sys.argv.index("--params")
        wantp = {"LATCH_DENOMINATOR": int(sys.argv[i + 1]), "CHECK_INVALID": int(sys.argv[i + 2])}
        pv = md.get("parameter_default_values", {})
        try:
            got = {k: int(v, 2) for k, v in pv.items()}
        except ValueError:
            got = dict(pv)
        if got != wantp:
            errors.append(f"parameters {got} != expected {wantp}")
    if nbits == 0:
        errors.append("no flop at all (the divider is sequential)")
    for e in errors[:20]:
        print("ERROR", e)
    params = {k: v for k, v in md.get("parameter_default_values", {}).items()}
    print(f"RESULT interface top={top} ports={sorted(ports)} params={ {k: int(v, 2) if set(v) <= set('01') else v for k, v in params.items()} } flop_bits={nbits} errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
