#!/usr/bin/env python3
"""revector.py <in.nl.v> <out.nl.v>: rename-only transform of a LibreLane (SYNTH_SPLITNETS) netlist.
The bit-split escaped wires \\name[k] become bits of one vector wire name[W-1:0], so that lemma files
can reference them as cand.name. No cell, pin or connection changes (checked: the cell section is
identical after the same name normalization)."""
import re, sys, collections
src = open(sys.argv[1]).read()
decl = re.compile(r"^\s*wire \\([A-Za-z_][\w.$]*)\[(\d+)\] ;\n", re.M)
bits = collections.defaultdict(set)
for m in decl.finditer(src): bits[m.group(1)].add(int(m.group(2)))
out = decl.sub("", src)
vec = "".join(f"  wire [{max(b)}:0] {n};\n" for n, b in sorted(bits.items()) if b == set(range(max(b) + 1)))
assert all(b == set(range(max(b) + 1)) for b in bits.values()), "non-contiguous split net"
i = out.index("\n", out.index(");")) + 1          # after the module port list
out = out[:i] + vec + out[i:]
out = re.sub(r"\\([A-Za-z_][\w$]*)\[(\d+)\] ", lambda m: f"{m.group(1)}[{m.group(2)}] " if m.group(1) in bits else m.group(0), out)
open(sys.argv[2], "w").write(out)
norm = lambda t: [l for l in re.sub(r"\\([A-Za-z_][\w$]*)\[(\d+)\] ", r"\1[\2] ", t).splitlines() if "wire" not in l]
print("vectors:", {n: max(b) + 1 for n, b in bits.items()}, "cell section identical:", norm(src) == norm(out))
