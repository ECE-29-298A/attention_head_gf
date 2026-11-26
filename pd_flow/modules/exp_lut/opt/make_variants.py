#!/usr/bin/env python3
"""make_variants.py <cand.v>... : cosmetic (function-preserving) rewrites of the weight logic,
applied identically to the golden (noise band) and to candidates (candidate spread).
Only the body between the port list and the REGISTERED generate block is touched.
  v1  mux select inversion:   s ? a : b          ->  !s ? b : a      (every ternary on shift bits)
  v2  case items in reverse order (default stays last)
  v3  logical -> bitwise:     || -> |,  && -> &
  v4  v1 + v3
  v5  v2 + v3
  v6  v1 + v2
  v7  W zeroing / saturation term moved to the end of each OR list (|| terms reversed)
  v8  'always @(*)' tables rewritten as 'always @*' with the case selector parenthesised
  v9  each || list rotated by one term (different OR association)
  v10 'if (ovf) zero else table' written as 'if (!(ovf)) table else zero'
  v11 reduction OR (|x[a:b]) written as (x[a:b] != 0)
Writes variants/<name>_v<k>.v; skips a variant that leaves the text unchanged."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(HERE, "variants"), exist_ok=True)


def split(src):
    a = src.index("output wire        [7:0] W")
    a = src.index("\n", src.index(");", a)) + 1
    b = src.index("if (REGISTERED) begin : g_registered")
    return src[:a], src[a:b], src[b:]


def v1(t):  # select inversion on 'shift[k] ? A : B' (A, B without nested ternaries)
    return re.sub(r"(?<![!\w])(shift\[\d\]) \? ((?:[^?:;{}\[\]]|\[[^\]]*\])+?) : ((?:[^?:;{}\[\]]|\[[^\]]*\])+?)([;,}])",
                  lambda m: f"!{m.group(1)} ? {m.group(3)} : {m.group(2)}{m.group(4)}", t)


def v2(t):
    def rev(m):
        head, body, tail = m.group(1), m.group(2), m.group(3)
        lines = body.rstrip("\n").split("\n")
        items = [l for l in lines if not l.strip().startswith("default")]
        dflt = [l for l in lines if l.strip().startswith("default")]
        return head + "\n".join(items[::-1] + dflt) + "\n" + tail
    return re.sub(r"(case \([^\n]*\)\n)(.*?\n)(\s*endcase)", rev, t, flags=re.S)


def v3(t):
    return t.replace("||", "|").replace("&&", "&")


def v7(t):
    def rev(m):
        terms = [x.strip() for x in re.split(r"\|\|", m.group(2))]
        return m.group(1) + " ||\n    ".join(terms[::-1]) + ";"
    return re.sub(r"(wire \w+ = )([^;]*\|\|[^;]*);", rev, t, flags=re.S)


def v8(t):
    t = t.replace("always @(*) begin", "always @* begin")
    return re.sub(r"case \(([^()\n]+)\)\n", r"case ((\1))\n", t)


def v9(t):  # rotate each || list by one term (changes the OR association)
    def rot(m):
        terms = [x.strip() for x in re.split(r"\|\|", m.group(2))]
        terms = terms[1:] + terms[:1]
        return m.group(1) + " ||\n    ".join(terms) + ";"
    return re.sub(r"(wire \w+ = )([^;]*\|\|[^;]*);", rot, t, flags=re.S)


def v10(t):  # if (X) zero else table  ->  if (!(X)) table else zero
    m = re.search(r"    if \((\w+(?: \|\| \w+(?:\[\d\])?)?)\) begin\n        weight = 8'd0;[^\n]*\n    end else begin\n(.*?\n)    end\nend", t, re.S)
    if not m: return t
    return t[:m.start()] + f"    if (!({m.group(1)})) begin\n{m.group(2)}    end else begin\n        weight = 8'd0;\n    end\nend" + t[m.end():]


def v11(t):  # reduction OR -> compare with zero
    return re.sub(r"\(\|(\w+\[\d+:\d+\])\)", r"(\1 != 0)", t)


V = {1: v1, 2: v2, 3: v3, 4: lambda t: v3(v1(t)), 5: lambda t: v3(v2(t)), 6: lambda t: v2(v1(t)),
     7: v7, 8: v8, 9: v9, 10: v10, 11: v11}
for f in sys.argv[1:]:
    name = os.path.basename(f)[:-2]
    src = open(f).read()
    h, body, tl = split(src)
    for k, fn in V.items():
        nb = fn(body)
        if nb == body:
            print(f"{name}_v{k}: unchanged, skipped"); continue
        open(os.path.join(HERE, "variants", f"{name}_v{k}.v"), "w").write(h + nb + tl)
        print(f"{name}_v{k}")
