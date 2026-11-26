#!/usr/bin/env python3
"""Lint and translate a candidate-supplied seq_eq lemma file (mac_unit SPEC.md section 5).

Adapted from pd_flow/modules/divider/verif/formal/lemma_prep.py (frozen, with review fixes F1/F2).
Changes: configurations are OUTPUTS = 2 / 4 / 8; the read-only miter observers fresh_s,
fresh_l and fresh_ring (SPEC 5.1) are whitelisted names; the miter module is mac_miter.

Lemma file format (SystemVerilog subset; anything else rejects the file):
  - comments (// and /* */) and blank lines;
  - statements  [label:] assert property ( <expression> ) ;
    where <expression> is a Boolean over hierarchical names of the two miter instances,
    gold.<name> (the golden) and cand.<name> (the candidate), and the read-only miter
    observers fresh_s, fresh_l, fresh_ring (flush state, SPEC 5.1), e.g.
        l_s: assert property (!fresh_s || cand.S == gold.S);
        l_r1: assert property (!fresh_ring[1] || cand.ring[39:20] == gold.ring[39:20]);
    <name> may contain generate-block dots and may be followed by a bit or part select.
    Constants, operators and $signed/$unsigned are allowed;
  - a configuration directive comment  // @config 2 | 4 | 8 | <list, e.g. 4 8> | all  that
    applies to the following statements (default all), because the ring width depends on
    OUTPUTS.
Rejected anywhere (word match, also inside the expression): assume, restrict, anyconst,
anyseq, anyinit, allconst, allseq, force, release, initial, always, assign, cover, wire, reg,
logic, module, include, define; a backtick; '@', '##', '|->', '|=>' (no temporal operators);
a single '=' (assignment). Every statement must reference at least one gold.* or cand.* name.

Every lemma becomes an ASSERTION in the miter, checked at every step from step 0 (free
start states), proven together with the port equality a_eq. Nothing is ever assumed. A lemma
that does not hold from arbitrary start states fails the base case; guard it with the
fresh_* observers.

Usage:
  lemma_prep.py lint <file>
  lemma_prep.py gen  <file|none> <config 2|4|8> <widths.json> <out.vh> <out_connect.ys>
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
        m = re.match(r"^\s*//\s*@config\s+((?:[248]\s*)+|all)\s*$", line)
        if m:
            out.append(f"\x00CONFIG {'_'.join(m.group(1).split())}\x00;")
            continue
        out.append(re.sub(r"//.*", "", line))
    return "\n".join(out)


# Review fix F2 (agent 2): a lemma expression is checked against a token WHITELIST, not
# only a keyword blacklist. Allowed: gold.*/cand.* names, numeric literals, $signed /
# $unsigned, pure operators, brackets and commas; for mac_unit also the three read-only
# observers fresh_s / fresh_l / fresh_ring (a read cannot change them: every assignment and
# side-effecting operator is rejected). Rejected: any other identifier (the miter's own
# load_o / head_f / clk / g_* / c_* and its inputs, keywords such as s_eventually, disable,
# iff, inside, always_comb) and every side-effecting operator (++, --, =, op=, <<=, >>=, ...).
TOKEN = re.compile(r"""\s+
  | (?P<hier>\b(?:gold|cand)\.[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)*)
  | (?P<num>\d*\s*'[sS]?[bBoOdDhH]\s*[0-9a-fA-F_xXzZ?]+|\d[\d_]*)
  | (?P<sys>\$(?:signed|unsigned)\b)
  | (?P<obs>\b(?:fresh_s|fresh_l|fresh_ring)\b(?!\s*\.))
  | (?P<op>===|!==|==|!=|<=|>=|&&|\|\||<<<|>>>|<<|>>|\*\*|~&|~\||~\^|\^~|[-+*/%&|^~!<>?:(){}\[\],])
""", re.X)


def expr_whitelist(expr):
    errs = []
    for bad in ("++", "--"):
        if bad in expr:
            errs.append(f"operator '{bad}' is not allowed")
    pos = 0   # a lone '=' is not a whitelisted token, so every assignment form is rejected
    while pos < len(expr):
        m = TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            errs.append(f"token not allowed in a lemma expression: {expr[pos:pos + 20]!r}")
            break
        pos = m.end()
    return errs


def parse(path):
    """Return (lemmas [(label, config, expr)], errors)."""
    raw = open(path).read()
    text = strip_comments(raw)
    errors = []
    body = re.sub(r"\x00CONFIG ([248_]+|all)\x00", "", text)
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
        m = re.match(r"^\s*\x00CONFIG ([248_]+|all)\x00\s*$", st)
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
        errors += [f"{label}: {e}" for e in expr_whitelist(expr)]
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
        if c != "all" and cfg not in c.split("_"):
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
                conn.append(f"connect -set {k} {full} mac_miter")
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
    vh.append("    always @* begin")
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
