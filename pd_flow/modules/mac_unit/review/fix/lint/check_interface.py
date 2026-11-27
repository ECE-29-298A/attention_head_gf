#!/usr/bin/env python3
"""Check a Yosys write_json netlist of mac_unit against the interface and structure contract
(SPEC.md R13, R14). Adapted from the frozen divider contract's check_interface.py.

Usage: check_interface.py <design.json> --outputs P [--params P]
--outputs P: the configuration (2, 4 or 8); sel is $clog2(P) bits wide.
--params P (RTL mode): the top module must have exactly one parameter, OUTPUTS = P (Yosys
     parameter_default_values; run_all.sh uses it on the chparam'd design and, without chparam,
     with 8 to enforce the DEFAULT of R13: the chip instantiates OUTPUTS explicitly, the cocotb
     block test relies on the default).
The JSON is written after `proc -noopt; flatten; check -assert; scc; opt_clean`.
R13 (interface): ports exactly clk, accum_mode, load, subtract (in, 1), M (in, 22), score_en
     (in, 1), qi, ki (in, 8), first, accum_en (in, 1), W (in, 8), sel (in, log2 P), v (in, 8),
     bit_sel (in, 3), S (out, 22), L (out, 12), O0 (out, 20). No other port; in particular NO
     reset input.
R14 (structure, power-up): every state element is a positive-edge D flop WITHOUT any
     asynchronous or synchronous reset/set ($dff, $dffe, $_DFF_P_, $_DFFE_PP_/PN_), clocked by
     the clk port; no latches, memories or $anyinit; no `init` attribute on any wire (the
     power-up state of the ring, S and L stays arbitrary, as in the golden); no black-box
     (non-primitive) cells after flatten. The NUMBER of flop bits is reported, not constrained.
"""
import json
import sys

ALLOWED = ("$dff", "$dffe", "$_DFF_P_", "$_DFFE_PP_", "$_DFFE_PN_")
STATE_PREFIXES = ("$ff", "$dff", "$adff", "$sdff", "$aldff", "$dlatch", "$adlatch", "$sr",
                  "$mem", "$anyinit", "$_FF_", "$_DFF", "$_SDFF", "$_DLATCH", "$_SR", "$_ALDFF")


def main() -> int:
    d = json.load(open(sys.argv[1]))
    P = int(sys.argv[sys.argv.index("--outputs") + 1])
    selw = {2: 1, 4: 2, 8: 3}[P]
    mods = d["modules"]
    tops = [m for m, x in mods.items() if x.get("attributes", {}).get("top")]
    errors = []
    if len(tops) != 1:
        errors.append(f"expected one top module, got {tops}")
    top = tops[0] if tops else next(iter(mods))
    md = mods[top]
    ports = {p: (x["direction"], len(x["bits"])) for p, x in md["ports"].items()}
    want = {"clk": ("input", 1), "accum_mode": ("input", 1), "load": ("input", 1),
            "subtract": ("input", 1), "M": ("input", 22), "score_en": ("input", 1),
            "qi": ("input", 8), "ki": ("input", 8), "first": ("input", 1),
            "accum_en": ("input", 1), "W": ("input", 8), "sel": ("input", selw),
            "v": ("input", 8), "bit_sel": ("input", 3),
            "S": ("output", 22), "L": ("output", 12), "O0": ("output", 20)}
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
                    errors.append(f"state cell {c} of type {t} (reset/set, latch, memory, negedge or init)")
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
        wantp = {"OUTPUTS": int(sys.argv[sys.argv.index("--params") + 1])}
        pv = md.get("parameter_default_values", {})
        try:
            got = {k: int(v, 2) for k, v in pv.items()}
        except ValueError:
            got = dict(pv)
        if got != wantp:
            errors.append(f"parameters {got} != expected {wantp}")
    if nbits == 0:
        errors.append("no flop at all (mac_unit is sequential)")
    # Review fix F1 (agent 2): no state beyond the golden's 20*P + 34 bits (ring, S, L).
    # fv_spec_P pins every trace from t >= P and forces >= 20*P + 34 behaviourally distinct
    # reachable states; with at most that many bits every power-up state is then equivalent
    # to a golden state, so O0 in the first P cycles cannot depend on the inputs (SPEC 7 gap).
    if nbits > 20 * P + 34:
        errors.append(f"{nbits} flop bits > {20 * P + 34} (golden ring + S + L): extra (hidden power-up) state")
    for e in errors[:20]:
        print("ERROR", e)
    params = {k: v for k, v in md.get("parameter_default_values", {}).items()}
    print(f"RESULT interface top={top} outputs={P} ports={len(ports)} params={ {k: int(v, 2) if set(v) <= set('01') else v for k, v in params.items()} } flop_bits={nbits} errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
