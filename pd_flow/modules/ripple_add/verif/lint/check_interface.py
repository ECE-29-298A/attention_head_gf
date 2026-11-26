#!/usr/bin/env python3
"""Check a Yosys write_json netlist of ripple_add against the interface and structure contract.

Usage: check_interface.py <design.json> <N>
R5: ports exactly {a: in [N-1:0], b: in [N-1:0], cin: in 1, s: out [N-1:0]}.
R3: no state cells (flops, latches, memories, word-level or gate-level) and no remaining
    non-primitive (black-box) cell instances in the elaborated, flattened module.
"""
import json
import sys

STATE_PREFIXES = ("$ff", "$dff", "$adff", "$sdff", "$aldff", "$dlatch", "$adlatch", "$sr",
                  "$mem", "$anyinit", "$_FF_", "$_DFF", "$_SDFF", "$_DLATCH", "$_SR", "$_ALDFF")


def main() -> int:
    path, n = sys.argv[1], int(sys.argv[2])
    with open(path) as f:
        design = json.load(f)
    mods = design["modules"]
    tops = [m for m, d in mods.items() if d.get("attributes", {}).get("top")]
    errors = []
    if len(tops) != 1:
        errors.append(f"expected one top module, got {tops}")
        top = next(iter(mods))
    else:
        top = tops[0]
    ports = {p: (d["direction"], len(d["bits"])) for p, d in mods[top]["ports"].items()}
    want = {"a": ("input", n), "b": ("input", n), "cin": ("input", 1), "s": ("output", n)}
    if ports != want:
        errors.append(f"ports {ports} != expected {want}")
    state = [(m, c, d["type"]) for m, md in mods.items() for c, d in md["cells"].items()
             if d["type"].startswith(STATE_PREFIXES)]
    if state:
        errors.append(f"state elements present: {state[:10]}")
    opaque = [(m, c, d["type"]) for m, md in mods.items() for c, d in md["cells"].items()
              if not d["type"].startswith("$")]
    if opaque:
        errors.append(f"unflattened / black-box cells present: {opaque[:10]}")
    for e in errors:
        print("ERROR", e)
    print(f"RESULT interface N={n} top={top} ports={sorted(ports)} state_cells={len(state)} "
          f"errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
