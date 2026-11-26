#!/usr/bin/env python3
"""Check a Yosys write_json netlist of max_reg against the interface and structure contract.

Usage: check_interface.py <design.json>
The JSON is written after `proc -noopt; flatten; check -assert; scc; opt_clean`.
R9  (interface): ports exactly clk (in, 1), first (in, 1), en (in, 1), S_in (in, 22),
     M (out, 22). No other port (in particular no reset).
R8  (no reset, no power-up value): every state element is a positive-edge D flop with no
     synchronous or asynchronous reset/set ($dff, $dffe, $_DFF_P_, $_DFFE_PP_/PN_), clocked by
     the clk port; no latches, memories or $anyinit; no `init` attribute on any wire.
R12 (state): exactly 22 flop bits. No black-box (non-primitive) cells after flatten.
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
    want = {"clk": ("input", 1), "first": ("input", 1), "en": ("input", 1),
            "S_in": ("input", 22), "M": ("output", 22)}
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
                    errors.append(f"state cell {c} of type {t} (reset, latch, memory, negedge or init)")
                    continue
                p = cd.get("parameters", {})
                if t in ("$dff", "$dffe") and int(p.get("CLK_POLARITY", "1"), 2) != 1:
                    errors.append(f"flop {c} is negative-edge")
                if t == "$dffe" and int(p.get("EN_POLARITY", "1"), 2) not in (0, 1):
                    errors.append(f"flop {c} bad enable polarity")
                ck = cd["connections"].get("CLK", cd["connections"].get("C"))
                if ck != clkbits:
                    errors.append(f"flop {c} clock {ck} is not the clk port {clkbits}")
                nbits += int(p.get("WIDTH", "1"), 2) if t in ("$dff", "$dffe") else 1
        for n, nd in x["netnames"].items():
            if "init" in nd.get("attributes", {}):
                errors.append(f"wire {m}.{n} has an init (power-up) value")
    if nbits != 22:
        errors.append(f"flop bits {nbits} != 22")
    for e in errors[:20]:
        print("ERROR", e)
    print(f"RESULT interface top={top} ports={sorted(ports)} flop_bits={nbits} errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
