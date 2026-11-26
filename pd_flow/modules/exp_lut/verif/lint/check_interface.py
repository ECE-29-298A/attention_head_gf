#!/usr/bin/env python3
"""Check a Yosys write_json netlist of exp_lut against the interface and structure contract.

Usage: check_interface.py <design.json> --registered N
The JSON is written after `proc -noopt -norom; flatten; check -assert; scc; opt_clean`
(the configuration already fixed: chparam for RTL, the netlist as is for gate level).
R13 (interface): ports exactly clk (in, 1), rst_n (in, 1), start (in, 1), D (in, 22),
     shift (in, 4), done (out, 1), W (out, 8). No other port.
R14 (structure):
  REGISTERED = 0: no state element at all (no flop, latch, memory, $anyinit).
  REGISTERED = 1: exactly 9 flop bits, every one a positive-edge D flop without
     asynchronous reset/set ($dff, $dffe, $_DFF_P_, $_DFFE_PP_/PN_; the synchronous reset
     is logic in front of the D input), clocked by the clk port; no latches or memories.
  Both: no `init` attribute on any wire (no power-up value); no black-box (non-primitive)
     cells after flatten.
"""
import json
import sys

ALLOWED = ("$dff", "$dffe", "$_DFF_P_", "$_DFFE_PP_", "$_DFFE_PN_")
STATE_PREFIXES = ("$ff", "$dff", "$adff", "$sdff", "$aldff", "$dlatch", "$adlatch", "$sr",
                  "$mem", "$anyinit", "$_FF_", "$_DFF", "$_SDFF", "$_DLATCH", "$_SR", "$_ALDFF")


def main() -> int:
    d = json.load(open(sys.argv[1]))
    reg = int(sys.argv[sys.argv.index("--registered") + 1])
    want_bits = 9 if reg else 0
    mods = d["modules"]
    tops = [m for m, x in mods.items() if x.get("attributes", {}).get("top")]
    errors = []
    if len(tops) != 1:
        errors.append(f"expected one top module, got {tops}")
    top = tops[0] if tops else next(iter(mods))
    md = mods[top]
    ports = {p: (x["direction"], len(x["bits"])) for p, x in md["ports"].items()}
    want = {"clk": ("input", 1), "rst_n": ("input", 1), "start": ("input", 1),
            "D": ("input", 22), "shift": ("input", 4), "done": ("output", 1), "W": ("output", 8)}
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
                if reg == 0:
                    errors.append(f"state cell {c} of type {t} in a REGISTERED=0 design")
                    continue
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
    if nbits != want_bits:
        errors.append(f"flop bits {nbits} != {want_bits}")
    for e in errors[:20]:
        print("ERROR", e)
    print(f"RESULT interface top={top} registered={reg} ports={sorted(ports)} flop_bits={nbits} errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
