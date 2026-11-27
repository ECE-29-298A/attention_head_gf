#!/usr/bin/env python3
"""Check a Yosys write_json netlist of attention_controller against the interface and structure
contract (SPEC.md R-IF, R-STRUCT). Adapted from the frozen mac_unit contract's check_interface.py.

Usage: check_interface.py <design.json> --outputs P [--params P]
--params P (RTL mode): the top must have exactly one parameter, OUTPUTS = P (run_all.sh also
     checks the DEFAULT, 8, without chparam: the TT top passes OUTPUTS explicitly, the existing
     tests rely on the default).
The JSON is written after `proc -noopt -norom; flatten; check -assert; scc; opt_clean`.
R-IF: ports exactly clk, rst_n, start (in 1), last, score_shift (in 4), cont (in 1), idle,
     spi_cs_n, spi_sck, spi_mosi, spi_mosi_oe (out 1), spi_io (in 4), out_valid (out 1),
     out_ready, out_shift (in 1), out_bit (out 1).
R-STRUCT: every state element is a positive-edge flop clocked by the clk port, with at most a
     SYNCHRONOUS reset/enable (the golden's reset is synchronous: rst_n is an ordinary data
     input); no asynchronous reset/set, latch, memory, $anyinit or `init` attribute; no
     black-box cell after flatten.
F1 (mac_unit review fix, carried over): the number of flop bits is at most the golden's at the
     same OUTPUTS (308 / 227 / 186 for P = 8 / 4 / 2, measured by this script on the snapshot).
     Extra state is the vector for a hidden power-up or mode flag; the golden count is minimal for
     the golden, and an area candidate has no reason to exceed it.
"""
import json
import sys

ALLOWED = ("$dff", "$dffe", "$sdff", "$sdffe", "$sdffce", "$_DFF_P_", "$_DFFE_PP_", "$_DFFE_PN_",
           "$_SDFF_PP0_", "$_SDFF_PP1_", "$_SDFF_PN0_", "$_SDFF_PN1_", "$_SDFFE_PP0P_", "$_SDFFE_PP1P_",
           "$_SDFFE_PN0P_", "$_SDFFE_PN1P_", "$_SDFFE_PP0N_", "$_SDFFE_PP1N_", "$_SDFFE_PN0N_", "$_SDFFE_PN1N_",
           "$_SDFFCE_PP0P_", "$_SDFFCE_PP1P_", "$_SDFFCE_PN0P_", "$_SDFFCE_PN1P_",
           "$_SDFFCE_PP0N_", "$_SDFFCE_PP1N_", "$_SDFFCE_PN0N_", "$_SDFFCE_PN1N_")
STATE_PREFIXES = ("$ff", "$dff", "$adff", "$sdff", "$aldff", "$dlatch", "$adlatch", "$sr",
                  "$mem", "$anyinit", "$_FF_", "$_DFF", "$_SDFF", "$_DLATCH", "$_SR", "$_ALDFF")
GOLDEN_BITS = {8: 308, 4: 227, 2: 186}


def main() -> int:
    d = json.load(open(sys.argv[1]))
    P = int(sys.argv[sys.argv.index("--outputs") + 1])
    mods = d["modules"]
    tops = [m for m, x in mods.items() if x.get("attributes", {}).get("top")]
    errors = []
    if len(tops) != 1:
        errors.append(f"expected one top module, got {tops}")
    top = tops[0] if tops else next(iter(mods))
    md = mods[top]
    ports = {p: (x["direction"], len(x["bits"])) for p, x in md["ports"].items()}
    want = {"clk": ("input", 1), "rst_n": ("input", 1), "start": ("input", 1), "last": ("input", 4),
            "score_shift": ("input", 4), "cont": ("input", 1), "idle": ("output", 1),
            "spi_cs_n": ("output", 1), "spi_sck": ("output", 1), "spi_mosi": ("output", 1),
            "spi_mosi_oe": ("output", 1), "spi_io": ("input", 4), "out_valid": ("output", 1),
            "out_ready": ("input", 1), "out_shift": ("input", 1), "out_bit": ("output", 1)}
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
                    errors.append(f"state cell {c} of type {t} (async reset/set, latch, memory, negedge or init)")
                    continue
                p = cd.get("parameters", {})
                if t.startswith("$") and not t.startswith("$_") and int(p.get("CLK_POLARITY", "1"), 2) != 1:
                    errors.append(f"flop {c} is negative-edge")
                ck = cd["connections"].get("CLK", cd["connections"].get("C"))
                if ck != clkbits:
                    errors.append(f"flop {c} clock {ck} is not the clk port {clkbits}")
                nbits += int(p.get("WIDTH", "1"), 2) if not t.startswith("$_") else 1
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
        errors.append("no flop at all")
    if nbits > GOLDEN_BITS[P]:
        errors.append(f"{nbits} flop bits > {GOLDEN_BITS[P]} (the golden's at OUTPUTS={P}): extra (hidden) state")
    for e in errors[:20]:
        print("ERROR", e)
    print(f"RESULT interface top={top} outputs={P} ports={len(ports)} flop_bits={nbits} bound={GOLDEN_BITS[P]} errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
