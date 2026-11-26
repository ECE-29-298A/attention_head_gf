#!/usr/bin/env python3
"""Lint and translate a candidate-supplied seq_eq lemma file (SPEC.md section 4, amendment A-1).

Lemma file format (SystemVerilog subset; anything else rejects the file):
  - comments (// and /* */) and blank lines;
  - statements  [label:] assert property ( <expression> ) ;
    where <expression> is a Boolean over hierarchical names of the two miter instances,
    gold.<name> (the golden) and cand.<name> (the candidate), e.g.
        l_q: assert property (cand.q_reg == gold.quotient);
    <name> may contain generate-block dots (gold.g_divisor.saved_divisor) and may be followed
    by a bit or part select. Constants, operators and $signed/$unsigned are allowed;
  - a configuration directive comment  // @config 00 | 11 | all  that applies to the following
    statements (default all), because the two configurations have different registers.
Rejected anywhere (word match, also inside the expression): assume, restrict, anyconst,
anyseq, anyinit, allconst, allseq, force, release, initial, always, assign, cover, wire, reg,
logic, module, include, define; a backtick; '@', '##', '|->', '|=>' (no temporal operators);
a single '=' (assignment). Every statement must reference at least one gold.* or cand.* name.

Every lemma becomes an ASSERTION in the miter, checked from cycle 1 on (after the cycle-0
reset edge), proven together with the port equality a_eq. Nothing is ever assumed.

Usage:
  lemma_prep.py lint <file>
  lemma_prep.py gen  <file|none> <config 00|11> <widths.json> <out.vh> <out_connect.ys>
    widths.json: Yosys write_json of the flattened miter (no lemmas), for the widths and
    signedness of the referenced nets; every referenced net must exist there.
"""
import json
import re
import sys

FORBID = ["assume", "restrict", "anyconst", "anyseq", "anyinit", "allconst", "allseq", "force",
          "release", "initial", "always", "assign", "cover", "wire", "reg", "logic", "module",
          "include", "define", "deassign", "fork", "task", "function"]
HIER = re.compile(r"\b(gold|cand)\.([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)*)")
STMT = re.compile(r"^\s*(?:([A-Za-z_]\w*)\s*:\s*)?assert\s+property\s*\((.*)\)\s*$", re.S)


def strip_comments(text):
    """Remove comments, keeping // @config directives as markers."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*//\s*@config\s+(00|11|all)\s*$", line)
        if m:
            out.append(f"\x00CONFIG {m.group(1)}\x00;")
            continue
        out.append(re.sub(r"//.*", "", line))
    return "\n".join(out)


def parse(path):
    """Return (lemmas [(label, config, expr)], errors)."""
    raw = open(path).read()
    text = strip_comments(raw)
    errors = []
    body = re.sub(r"\x00CONFIG (00|11|all)\x00", "", text)
    for w in FORBID:
        if re.search(rf"(?<![\w$.]){re.escape(w)}\b|\${re.escape(w)}\b", body):
            errors.append(f"forbidden keyword '{w}'")
    for tok in ("`", "@", "##", "|->", "|=>"):
        if tok in body:
            errors.append(f"forbidden token '{tok}'")
    if re.search(r"(?<![=!<>])=(?![=])", body):
        errors.append("single '=' (assignment) is not allowed")
    lemmas, cfg, n = [], "all", 0
    for st in text.split(";"):
        if not st.strip():
            continue
        m = re.match(r"^\s*\x00CONFIG (00|11|all)\x00\s*$", st)
        if m:
            cfg = m.group(1)
            continue
        m = STMT.match(st)
        if not m:
            errors.append(f"not an 'assert property (...)' statement: {st.strip()[:80]!r}")
            continue
        n += 1
        label = m.group(1) or f"lemma_{n}"
        expr = m.group(2)
        if not HIER.search(expr):
            errors.append(f"{label}: references no gold.* / cand.* name")
        lemmas.append((label, cfg, expr))
    labels = [l for l, _, _ in lemmas]
    if len(set(labels)) != len(labels):
        errors.append("duplicate lemma labels")
    return raw, lemmas, errors


def lint(path):
    _, lemmas, errors = parse(path)
    for e in errors:
        print("REJECT", e)
    print(f"RESULT lemma_lint statements={len(lemmas)} errors={len(errors)}")
    return 1 if errors else 0


def gen(path, cfg, widths, out_vh, out_ys):
    if path == "none":
        open(out_vh, "w").write("// no lemma file\n")
        open(out_ys, "w").write("# no lemma file\n")
        print("RESULT lemma_gen lemmas=0 nets=0 errors=0")
        return 0
    _, lemmas, errors = parse(path)
    if errors:
        for e in errors:
            print("REJECT", e)
        print(f"RESULT lemma_gen lemmas=0 nets=0 errors={len(errors)}")
        return 1
    d = json.load(open(widths))
    top = [m for m, x in d["modules"].items() if x.get("attributes", {}).get("top")]
    nets = d["modules"][top[0]]["netnames"]
    decl, conn, body, used = [], [], [], {}
    for label, c, expr in lemmas:
        if c not in ("all", cfg):
            continue

        def rep(m):
            full = f"{m.group(1)}.{m.group(2)}"
            if full not in nets:
                errors.append(f"{label}: net {full} does not exist in configuration {cfg}")
                return "1'b0"
            if full not in used:
                k = f"lw_{len(used)}"
                used[full] = k
                nd = nets[full]
                w = len(nd["bits"])
                sg = "signed " if nd.get("signed") else ""
                decl.append(f"    wire {sg}[{w - 1}:0] {k};  // {full}")
                conn.append(f"connect -set {k} {full} divider_miter")
            return used[full]
        e2 = HIER.sub(rep, expr)
        body.append(f"        {label}: assert ({e2});")
    if errors:
        for e in errors:
            print("REJECT", e)
        print(f"RESULT lemma_gen lemmas=0 nets={len(used)} errors={len(errors)}")
        return 1
    vh = ["// generated by formal/lemma_prep.py from the candidate lemma file (assertions only)"]
    vh += decl
    vh.append("    always @* if (seen) begin")
    vh += body
    vh.append("    end")
    open(out_vh, "w").write("\n".join(vh) + "\n")
    open(out_ys, "w").write("\n".join(conn) + "\n")
    print(f"RESULT lemma_gen config={cfg} lemmas={len(body)} nets={len(used)} errors=0")
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "lint":
        sys.exit(lint(sys.argv[2]))
    sys.exit(gen(*sys.argv[2:7]))
