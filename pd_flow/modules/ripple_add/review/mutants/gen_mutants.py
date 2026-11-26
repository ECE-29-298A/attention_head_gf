#!/usr/bin/env python3
"""Generate ripple_add mutants from the golden RTL (Agent 2 review).

Each mutant is a single, deliberate fault applied to a copy of
pd_flow/baseline/original_rtl/ripple_add.v. The golden file is only read.
Writes <name>.v next to this script and mutants.json (name, class, description, intent).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "..", "..", "..", "..", "baseline", "original_rtl", "ripple_add.v")
SRC = open(GOLDEN).read()

GS = "assign s[i]     = a[i] ^ b[i] ^ c[i];"
GC = "assign c[i + 1] = (a[i] & b[i]) | (c[i] & (a[i] ^ b[i]));"
C0 = "assign c[0] = cin;"
LOOP = "for (i = 0; i < N; i = i + 1)"
HDR = "module ripple_add #(parameter N = 16) ("
for frag in (GS, GC, C0, LOOP, HDR):
    assert SRC.count(frag) == 1, frag

MUT = []  # (name, class, description, intent, [(old, new), ...])


def m(name, cls, desc, intent, *subs):
    MUT.append((name, cls, desc, intent, list(subs)))


# ---- structural / operator faults ------------------------------------------------
m("m01_sum_xor_to_or", "operator", "sum: second XOR changed to OR, s[i] = (a^b) | c[i]",
  "killed", (GS, "assign s[i]     = (a[i] ^ b[i]) | c[i];"))
m("m02_no_generate", "carry", "carry generate term a&b dropped", "killed",
  (GC, "assign c[i + 1] = c[i] & (a[i] ^ b[i]);"))
m("m03_no_propagate", "carry", "carry propagate term c&(a^b) dropped", "killed",
  (GC, "assign c[i + 1] = a[i] & b[i];"))
m("m04_carry_wrong_index", "carry", "sum bit i uses carry c[i-1] (bit 0 uses c[0])", "killed",
  (GS, "assign s[i]     = a[i] ^ b[i] ^ c[(i == 0) ? 0 : i - 1];"))
m("m05_cin_ignored", "cin", "cin ignored: c[0] tied to 0", "killed",
  (C0, "assign c[0] = 1'b0;"))
m("m06_bit0_sum_no_cin", "bit0/cin1", "bit-0 sum drops cin (carry still uses it); differs only when cin=1",
  "killed", (GS, "assign s[i]     = (i == 0) ? (a[i] ^ b[i]) : (a[i] ^ b[i] ^ c[i]);"))
m("m07_msb_no_carry_in", "msb", "MSB-only fault: s[N-1] ignores its carry in", "killed",
  (GS, "assign s[i]     = (i == N - 1) ? (a[i] ^ b[i]) : (a[i] ^ b[i] ^ c[i]);"))
m("m08_loop_bound_short", "loop", "loop bound off by one (i < N-1): s[N-1] undriven", "killed",
  (LOOP, "for (i = 0; i < N - 1; i = i + 1)"))
m("m09_stuck_at0_bit5", "stuck-at", "s[5] stuck at 0 (no effect for N <= 5)", "killed",
  (GS, "assign s[i]     = (i == 5) ? 1'b0 : (a[i] ^ b[i] ^ c[i]);"))
m("m10_stuck_at1_msb", "stuck-at", "s[N-1] stuck at 1", "killed",
  (GS, "assign s[i]     = (i == N - 1) ? 1'b1 : (a[i] ^ b[i] ^ c[i]);"))
m("m11_b_bit_reversed", "wiring", "operand b bit-reversed (b[N-1-i])", "killed",
  (GS, "assign s[i]     = a[i] ^ b[N - 1 - i] ^ c[i];"),
  (GC, "assign c[i + 1] = (a[i] & b[N - 1 - i]) | (c[i] & (a[i] ^ b[N - 1 - i]));"))
# ---- parameter-specific faults ------------------------------------------------------
m("m12_n22_only_bit20", "N=22 only", "only at N=22: bit-20 carry out = a&b | c (propagate qualifier lost)",
  "killed", (GC, "assign c[i + 1] = (N == 22 && i == 20) ? ((a[i] & b[i]) | c[i])"
                 " : ((a[i] & b[i]) | (c[i] & (a[i] ^ b[i])));"))
m("m13_n12_only_msb", "N=12 only", "only at N=12: carry into bit 11 dropped from the sum", "killed",
  (GS, "assign s[i]     = (N == 12 && i == 11) ? (a[i] ^ b[i]) : (a[i] ^ b[i] ^ c[i]);"))
m("m14_n22_only_cin1", "N=22 only, cin=1 only",
  "only at N=22 and cin=1: carry into bit 21 suppressed (breaks mac_unit subtract MSB)", "killed",
  (GS, "assign s[i]     = (N == 22 && i == N - 1) ? (a[i] ^ b[i] ^ (c[i] & ~cin))"
       " : (a[i] ^ b[i] ^ c[i]);"))
m("m15_cin1_full_chain", "cin=1 only",
  "only when cin=1 and the carry ripples through every bit (a^b == all ones): s[N-1] flipped",
  "killed",
  (GS, "assign s[i]     = a[i] ^ b[i] ^ c[i] ^ (i == N - 1 && cin && ((a ^ b) == {N{1'b1}}));"))
# ---- rare-pattern faults (sampling cannot be relied on) ---------------------------
KDEF = ("    wire [N:0] c;",
        "    localparam [63:0] KA = 64'h9E3779B97F4A7C15, KB = 64'hD1B54A32D192ED03;\n"
        "    localparam [63:0] KC = 64'h0000000000000ABC, KD = 64'h00000000000009F0;\n"
        "    wire [N:0] c;")
m("m16_rare_n22", "rare pattern, N=22 only",
  "only at N=22 for the single input a=KA[21:0], b=KB[21:0], cin=1: s[0] flipped (1 of 2^45 inputs)",
  "killed (formal only expected)", KDEF,
  (GS, "assign s[i]     = a[i] ^ b[i] ^ c[i] ^ (N == 22 && i == 0 && a == KA[N-1:0] && b == KB[N-1:0] && cin);"))
m("m17_rare_all_n", "rare pattern, all N",
  "every N: for the single input a=KA[N-1:0], b=KB[N-1:0], cin=0: s[0] flipped",
  "killed (formal/exhaustive only expected)", KDEF,
  (GS, "assign s[i]     = a[i] ^ b[i] ^ c[i] ^ (i == 0 && a == KA[N-1:0] && b == KB[N-1:0] && !cin);"))
m("m18_rare_n12_window", "rare pattern, N=12 only, outside mac_unit L range",
  "only at N=12 for a=12'hABC, b=12'h9F0 (b >= 256), cin=1: s[11] flipped",
  "killed (formal/exhaustive only expected)", KDEF,
  (GS, "assign s[i]     = a[i] ^ b[i] ^ c[i] ^ (N == 12 && i == N - 1 && a == KC[N-1:0] && b == KD[N-1:0] && cin);"))
# ---- non-functional contract items -------------------------------------------------
m("m19_latch", "statelessness",
  "output through an always @* latch that holds when a==b==all ones (else transparent)",
  "killed",
  ("output wire [N-1:0] s\n);",
   "output reg  [N-1:0] s\n);\n    wire [N-1:0] s_g;\n"
   "    always @* if (!(a == {N{1'b1}} && b == {N{1'b1}})) s = s_g;"),
  (GS, "assign s_g[i]   = a[i] ^ b[i] ^ c[i];"))
m("m20_default_n8", "interface", "default parameter changed N=16 -> N=8 (function at given N unchanged)",
  "killed by interface check only", (HDR, "module ripple_add #(parameter N = 8) ("))
m("m21_x_on_zero", "4-state", "s[0] = 1'bx when a==0, b==0, cin==0 (X output on a directed corner)",
  "killed",
  (GS, "assign s[i]     = (i == 0 && a == {N{1'b0}} && b == {N{1'b0}} && !cin) ? 1'bx : (a[i] ^ b[i] ^ c[i]);"))
m("m22_comb_loop", "statelessness/loop",
  "functionally redundant combinational loop: c[0] = cin | (s[N-1] & ~s[N-1])", "killed",
  (C0, "assign c[0] = cin | (s[N-1] & ~s[N-1]);"))
# ---- equivalent candidates (must survive; proven equivalent separately) ------------
m("e01_carry_or", "equivalent", "carry propagate qualifier a|b instead of a^b", "survive (equivalent)",
  (GC, "assign c[i + 1] = (a[i] & b[i]) | (c[i] & (a[i] | b[i]));"))
m("e02_carry_majority", "equivalent", "carry as majority(a, b, c)", "survive (equivalent)",
  (GC, "assign c[i + 1] = (a[i] & b[i]) | (a[i] & c[i]) | (b[i] & c[i]);"))
m("e03_behavioural", "equivalent", "behavioural s = a + b + cin (no ripple chain, no c[N])",
  "survive (equivalent)", None)


def main() -> int:
    meta = []
    for name, cls, desc, intent, subs in MUT:
        if subs == [None]:
            text = ("// MUTANT e03_behavioural: behavioural adder, functionally equivalent\n"
                    "module ripple_add #(parameter N = 16) (\n"
                    "    input  wire [N-1:0] a,\n    input  wire [N-1:0] b,\n"
                    "    input  wire         cin,\n    output wire [N-1:0] s\n);\n"
                    "    assign s = a + b + {{(N-1){1'b0}}, cin};\nendmodule\n")
        else:
            text = SRC
            for old, new in subs:
                assert text.count(old) == 1, (name, old)
                text = text.replace(old, new)
            text = f"// MUTANT {name}: {desc}\n// Derived from the golden ripple_add.v.\n" + text
        assert text != SRC
        with open(os.path.join(HERE, name + ".v"), "w") as f:
            f.write(text)
        meta.append({"name": name, "class": cls, "description": desc, "intent": intent,
                     "file": f"mutants/{name}.v"})
    json.dump(meta, open(os.path.join(HERE, "mutants.json"), "w"), indent=2)
    print(f"wrote {len(meta)} mutants")
    return 0


if __name__ == "__main__":
    sys.exit(main())
