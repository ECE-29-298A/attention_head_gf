#!/usr/bin/env python3
"""Generate operand-order permutations of several carry formulations (module-level search)."""
import random, itertools, os, sys
random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
HDR = """// ripple_add search variant {name}: s = (a + b + cin) mod 2^N
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output wire [N-1:0] s
);
"""
def sh(*xs):
    xs = list(xs); random.shuffle(xs); return xs
def AND(*x): return "(" + " & ".join(sh(*x)) + ")"
def OR(*x): return "(" + " | ".join(sh(*x)) + ")"
def XOR(*x): return "(" + " ^ ".join(sh(*x)) + ")"
A, B = "a[i]", "b[i]"
fams = {
 # true-polarity carry c[i]
 "gold": lambda K: (XOR(A, B, K), OR(AND(A, B), AND(K, XOR(A, B)))),
 "maj":  lambda K: (XOR(A, B, K), OR(AND(A, B), AND(A, K), AND(B, K))),
 "orp":  lambda K: (XOR(A, B, K), OR(AND(A, B), AND(K, OR(A, B)))),
 "pos":  lambda K: (XOR(A, B, K), AND(OR(A, B), OR(AND(A, B), K))),
 "pos3": lambda K: (XOR(A, B, K), AND(OR(A, B), OR(A, K), OR(B, K))),
 "mux":  lambda K: (XOR(A, B, K), f"({XOR(A,B)} ? {K} : {random.choice([A,B])})"),
}
alt = {
 # alternating polarity: even stages true c, odd stages k = ~c
 "alt_maj": (lambda K: (XOR(A, B, K), "~" + OR(AND(A, B), AND(A, K), AND(B, K))),
             lambda K: ("~" + XOR(A, B, K), "~" + OR(AND("~"+A, "~"+B), AND("~"+A, K), AND("~"+B, K)))),
 "alt_aoi": (lambda K: (XOR(A, B, K), "~" + OR(AND(A, B), AND(K, OR(A, B)))),
             lambda K: ("~" + XOR(A, B, K), "~(~" + AND(A, B) + " & (~" + OR(A, B) + f" | {K}))")),
}
def body(f_even, f_odd):
    se, ce = f_even("k[i]"); so, co = f_odd("k[i]")
    return f"""    wire [N-1:0] k;
    assign k[0] = cin;
    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : fa
            if (i % 2 == 0) begin : g_e
                assign s[i] = {se};
                if (i < N - 1) begin : g_c
                    assign k[i + 1] = {ce};
                end
            end else begin : g_o
                assign s[i] = {so};
                if (i < N - 1) begin : g_c
                    assign k[i + 1] = {co};
                end
            end
        end
    endgenerate
endmodule
"""
os.makedirs("v", exist_ok=True)
nper = int(sys.argv[2]) if len(sys.argv) > 2 else 6
for fam, f in fams.items():
    for j in range(nper):
        name = f"{fam}_{j}"
        open(f"v/{name}.v", "w").write(HDR.format(name=name) + body(f, f))
for fam, (fe, fo) in alt.items():
    for j in range(nper):
        name = f"{fam}_{j}"
        open(f"v/{name}.v", "w").write(HDR.format(name=name) + body(fe, fo))
