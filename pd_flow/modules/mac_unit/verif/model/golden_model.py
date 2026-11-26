#!/usr/bin/env python3
"""Executable model of the mac_unit next-state equations (SPEC.md R1-R12), written from the
SPEC with plain integer arithmetic. State: S (22 bits), L (12 bits) and the ring of OUTPUTS
20-bit slots (slot 0 = head = O0); None = unknown (power-up value, never written from inputs).

Commands:
  selftest                      checks the model against the high-level meaning (SPEC 2):
                                dot products (pass 1 and pass 2), V accumulation per
                                component, the weight sum L, plus hand-computed single steps.
  edges --outputs P --out FILE  edge-case + spot-check cycle vectors for sim/tb_edge.sv:
        [--random N --seed S]   one line per clock, inputs then the expected CURRENT outputs
                                (before that clock's edge), each with a known flag.
  refpoints --out FILE          (state, inputs) -> (S_n, L_n, tail_n) points for sim/tb_ref.sv,
        [--random N --seed S]   which checks formal/ref_mac_next.v against this model.
Every command prints a RESULT line and exits non-zero on a failure.
"""
import argparse
import hashlib
import random
import sys

M20, M22, M12 = (1 << 20) - 1, (1 << 22) - 1, (1 << 12) - 1
FIELDS = ("am", "load", "sub", "M", "se", "qi", "ki", "first", "ae", "W", "sel", "v", "bs")


def sx(x, n):
    x &= (1 << n) - 1
    return x - (1 << n) if x >> (n - 1) else x


def bw(b):
    """weight of bit b of a two's-complement byte"""
    return -128 if b == 7 else 1 << b


def inp(**kw):
    d = dict.fromkeys(FIELDS, 0)
    d.update(kw)
    return d


def next_state(S, L, O0, i):
    """(S_n, L_n, tail_n) from the current S, L, O0 (None = unknown) and the inputs i."""
    b = i["bs"]
    w = bw(b)
    load_o = bool(i["ae"] and i["first"] and b == 7)                   # R6
    vterm = i["W"] * w if (i["ae"] and (i["v"] >> b) & 1) else 0       # R5
    head = 0 if load_o else (None if O0 is None else sx(O0, 20))
    acc = None if head is None else head + vterm
    tail = (None if acc is None else acc & M20) if i["am"] else O0     # R7, R8
    if i["load"]:                                                       # R3
        S_n = i["M"] & M22 if i["sub"] else 0
    elif i["se"]:
        if i["am"]:                                                     # R4
            S_n = None if acc is None else acc & M22
        else:                                                           # R1, R2
            d = sx(i["qi"], 8) * (w if (i["ki"] >> b) & 1 else 0)
            S_n = None if S is None else (sx(S, 22) + (-d if i["sub"] else d)) & M22
    else:
        S_n = S
    if i["ae"] and i["sel"] == 0 and b == 0:                            # R10
        base = 0 if i["first"] else L
        L_n = None if base is None else (base + i["W"]) & M12
    else:
        L_n = L
    return S_n, L_n, tail


class Mac:
    def __init__(self, P):
        self.P = P
        self.S = self.L = None
        self.ring = [None] * P

    def outputs(self):
        return self.S, self.L, self.ring[0]

    def clock(self, i):
        assert 0 <= i["sel"] < self.P
        self.S, self.L, tail = next_state(self.S, self.L, self.ring[0], i)
        self.ring = self.ring[1:] + [tail]                                # R7: rotate


# ---------------------------------------------------------------- programs (cycle lists)
def score_row(q, k, subtract, M, rnd, ctrl_form=True):
    """Controller-like score row (attention_controller lines 98-104): per dimension 8 clocks
    without score_en (Q byte shifts in; load during dimension 0), then 8 clocks of K bits MSB
    first with score_en. ki is the serial bit replicated (ctrl_form) or the whole byte."""
    cyc = []
    for d, (qd, kd) in enumerate(zip(q, k)):
        for j in range(8):
            cyc.append(inp(load=int(d == 0), sub=subtract, M=M, qi=rnd.randrange(256),
                           ki=rnd.randrange(256), bs=7 - j, W=rnd.randrange(256),
                           v=rnd.randrange(256), first=rnd.randrange(2)))
        for j in range(8):
            b = 7 - j
            kb = (kd >> b) & 1
            cyc.append(inp(se=1, sub=subtract, M=M, qi=qd & 255,
                           ki=(255 if kb else 0) if ctrl_form else kd & 255, bs=b,
                           W=rnd.randrange(256), v=rnd.randrange(256), first=rnd.randrange(2)))
    return cyc


def v_block(P, W, vrow, first, ctrl_form=True):
    """One token's V block: bit planes MSB first, components 0..P-1 within a plane; the ring
    head is component c in the clock with sel = c (block starts aligned)."""
    cyc = []
    for j in range(8):
        b = 7 - j
        for c in range(P):
            vb = (vrow[c] >> b) & 1
            cyc.append(inp(am=1, ae=1, first=int(first), W=W, sel=c, bs=b,
                           v=(255 if vb else 0) if ctrl_form else vrow[c] & 255))
    return cyc


def run(m, cycles, out=None, cls="x"):
    for i in cycles:
        if out is not None:
            out.append((dict(i), m.outputs(), cls))
        m.clock(i)


def dot(q, k):
    return sum(sx(a, 8) * sx(b, 8) for a, b in zip(q, k))


# ---------------------------------------------------------------- selftest
def selftest():
    fails, n = [], 0
    rnd = random.Random(11)

    def chk(name, got, want):
        nonlocal n
        n += 1
        if got != want:
            fails.append(f"{name}: got {got} want {want}")

    # hand-computed single steps (R1/R2 sign handling, R3, R5/R6, R10)
    chk("score b7 add", next_state(0, 0, 0, inp(se=1, qi=0x80, ki=0x80, bs=7))[0], 16384)
    chk("score b7 sub", next_state(0, 0, 0, inp(se=1, sub=1, qi=0x7F, ki=0x80, bs=7))[0], 16256)
    chk("score b0 neg", next_state(0, 0, 0, inp(se=1, qi=0x80, ki=1, bs=0))[0], (-128) & M22)
    chk("score kbit 0", next_state(5, 0, 0, inp(se=1, qi=0x80, ki=0x7F, bs=7))[0], 5)
    chk("load sub", next_state(1, 0, 0, inp(load=1, sub=1, M=0x200000, se=1))[0], 0x200000)
    chk("load 0", next_state(1, 0, 0, inp(load=1, se=1, ki=255, qi=3))[0], 0)
    chk("acc first b7", next_state(0, 0, 77, inp(am=1, ae=1, first=1, bs=7, W=255, v=0x80))[2], (-32640) & M20)
    chk("acc first b6", next_state(0, 0, 77, inp(am=1, ae=1, first=1, bs=6, W=255, v=0x40))[2], 77 + 255 * 64)
    chk("acc en0", next_state(0, 0, 77, inp(am=1, ae=0, first=1, bs=7, W=255, v=0xFF))[2], 77)
    chk("score mode ring", next_state(0, 0, 77, inp(am=0, ae=1, first=1, bs=7, W=255, v=0xFF))[2], 77)
    chk("L first", next_state(0, 100, 0, inp(ae=1, first=1, W=9, bs=0, sel=0))[1], 9)
    chk("L add", next_state(0, 100, 0, inp(ae=1, W=9, bs=0, sel=0))[1], 109)
    chk("L sel1", next_state(0, 100, 0, inp(ae=1, W=9, bs=0, sel=1))[1], 100)
    chk("L wrap", next_state(0, 4090, 0, inp(ae=1, W=9, bs=0))[1], 3)
    chk("S in accum", next_state(0, 0, (-5) & M20, inp(am=1, se=1, ae=1, bs=7, v=0x80, W=1))[0], (-133) & M22)

    # semantics: dot products (pass 1 = sum, pass 2 = M - sum) and V accumulation
    for P in (2, 4, 8):
        for trial in range(6):
            dims = 64 if trial < 2 else rnd.choice((1, 2, 3, 5))
            if trial == 0:
                q, k = [0x80] * dims, [0x80] * dims
            elif trial == 1:
                q, k = [0x80] * dims, [0x7F] * dims
            else:
                q = [rnd.randrange(256) for _ in range(dims)]
                k = [rnd.randrange(256) for _ in range(dims)]
            M = rnd.randrange(1 << 22) if trial % 2 else 0x1FFFFF
            m = Mac(P)
            run(m, score_row(q, k, 0, M, rnd, trial % 2 == 0))
            chk(f"P{P} pass1 dot", m.S, dot(q, k) & M22)
            run(m, score_row(q, k, 1, M, rnd))
            chk(f"P{P} pass2 M-dot", m.S, (sx(M, 22) - dot(q, k)) & M22)
            T = 16 if trial < 2 else rnd.choice((1, 2, 3))
            Ws = [255] * T if trial < 2 else [rnd.randrange(256) for _ in range(T)]
            V = [[(0x80 if trial == 0 else 0x7F) if trial < 2 else rnd.randrange(256)
                  for _ in range(P)] for _ in range(T)]
            m = Mac(P)
            for t in range(T):
                run(m, v_block(P, Ws[t], V[t], t == 0, t % 2 == 0))
                run(m, score_row(q[:1], k[:1], 0, 0, rnd))     # a score row between tokens (16 clocks)
            for c in range(P):
                chk(f"P{P} V comp {c}", m.ring[c], sum(Ws[t] * sx(V[t][c], 8) for t in range(T)) & M20)
            chk(f"P{P} L", m.L, sum(Ws) & M12)
    for f in fails[:20]:
        print("FAIL", f)
    print(f"RESULT selftest checks={n} failures={len(fails)}")
    return 1 if fails else 0


# ---------------------------------------------------------------- edges for tb_edge
EXT8 = (0x80, 0x81, 0xFF, 0x00, 0x01, 0x7F, 0x55, 0xAA)
EXTW = (0, 1, 127, 128, 255)
EXTM = (0x200000, 0x200001, 0x3FFFFF, 0, 1, 0x1FFFFF, 0x155555)


def edges(P, nrand, seed):
    rnd = random.Random(seed)
    m = Mac(P)
    out = []
    # 0. power-up: everything unknown; flush exactly as the controller does
    run(m, [inp(load=1)], out, "flush")
    run(m, v_block(P, 3, [rnd.randrange(256) for _ in range(P)], True), out, "flush")
    assert None not in m.outputs() and None not in m.ring
    # 1. controller-like rows: extremes and random, pass 1 and pass 2, both ki forms
    for trial in range(4):
        dims = 64 if trial == 0 else 4
        q = [0x80] * dims if trial == 0 else [rnd.choice(EXT8) for _ in range(dims)]
        k = [0x80] * dims if trial == 0 else [rnd.choice(EXT8) for _ in range(dims)]
        for sub in (0, 1):
            run(m, score_row(q, k, sub, rnd.choice(EXTM), rnd, trial % 2 == 0), out, "score_row")
    # 2. V accumulation of 16 tokens at the extremes (|O| = 522240), then 3 random tokens;
    #    score rows between tokens (ring holds while scoring), then a hold read-out
    for Vx in (0x80, 0x7F):
        for t in range(16):
            run(m, v_block(P, 255, [Vx] * P, t == 0, t % 2 == 0), out, "v_extreme")
            run(m, score_row([rnd.randrange(256)], [rnd.randrange(256)], t & 1, 0, rnd), out, "v_extreme")
        run(m, [inp(am=1, sel=c % P, W=255, v=255, bs=c % 8, first=1) for c in range(2 * P)], out, "readout")
    for t in range(3):
        run(m, v_block(P, rnd.randrange(256), [rnd.randrange(256) for _ in range(P)], t == 0), out, "v_random")
    run(m, [inp(am=1, sel=c % P) for c in range(P)], out, "readout")
    # 3. single-step score extremes: every qi x ki extreme x bit_sel x subtract, S reloaded
    for Mv in EXTM:
        for sub in (0, 1):
            run(m, [inp(load=1, sub=1, M=Mv)], out, "score_step")
            for qv in EXT8:
                for kv in EXT8[:4]:
                    for b in range(8):
                        run(m, [inp(se=1, sub=sub, qi=qv, ki=kv, bs=b, sel=rnd.randrange(P))], out, "score_step")
    # 4. single-step accumulate extremes: W x v x bit_sel x first (accum_en = 1), and holds
    for Wv in EXTW:
        for vv in EXT8:
            for b in range(8):
                for f in (0, 1):
                    run(m, [inp(am=1, ae=1, first=f, W=Wv, v=vv, bs=b, sel=rnd.randrange(P))], out, "acc_step")
                run(m, [inp(am=1, ae=0, first=1, W=Wv, v=vv, bs=b, sel=0)], out, "acc_hold")
    # 5. L: sel 0 / non-zero, bit_sel 0 / non-zero, first, wrap past 4095
    for f in (1, 0, 0):
        for s in range(P):
            for b in (0, 7, 3):
                run(m, [inp(ae=1, am=rnd.randrange(2), first=f, W=255, sel=s, bs=b)], out, "L")
    run(m, [inp(ae=1, W=255, sel=0, bs=0) for _ in range(20)], out, "L_wrap")
    # 6. mode switches and off-protocol combinations (behaviour is still defined, SPEC R4/R9)
    for _ in range(60):
        run(m, [inp(am=rnd.randrange(2), se=1, ae=rnd.randrange(2), load=int(rnd.random() < 0.1),
                    sub=rnd.randrange(2), M=rnd.choice(EXTM), qi=rnd.choice(EXT8), ki=rnd.choice(EXT8),
                    first=rnd.randrange(2), W=rnd.choice(EXTW), v=rnd.choice(EXT8), bs=rnd.choice((0, 7)),
                    sel=rnd.randrange(P))], out, "mode_mix")
    # 7. spot checks: fully random inputs
    for _ in range(nrand):
        run(m, [inp(am=rnd.randrange(2), load=int(rnd.random() < 0.05), sub=rnd.randrange(2),
                    M=rnd.randrange(1 << 22), se=rnd.randrange(2), qi=rnd.randrange(256),
                    ki=rnd.randrange(256), first=int(rnd.random() < 0.2), ae=rnd.randrange(2),
                    W=rnd.randrange(256), sel=rnd.randrange(P), v=rnd.randrange(256),
                    bs=rnd.randrange(8))], out, "random")
    run(m, [inp()], out, "final")
    return out


def write_edges(P, nrand, seed, path):
    rows = edges(P, nrand, seed)
    lines = []
    cnt = {}
    for i, (S, L, O), cls in rows:
        f = [i[k] for k in FIELDS]
        o = [int(S is not None), S or 0, int(L is not None), L or 0, int(O is not None), O or 0]
        lines.append(" ".join(f"{x:x}" for x in f + o) + f" {cls}")
        cnt[cls] = cnt.get(cls, 0) + 1
    text = "\n".join(lines) + "\n"
    open(path, "w").write(text)
    known = sum(1 for _, o, _ in rows if None not in o)
    print("classes:", " ".join(f"{k}={v}" for k, v in cnt.items()))
    print(f"RESULT edges outputs={P} cycles={len(rows)} fully_known={known} "
          f"sha256={hashlib.sha256(text.encode()).hexdigest()[:16]}")
    return 0


def write_refpoints(nrand, seed, path):
    rnd = random.Random(seed)
    pts = []
    for S in (0, 0x1FFFFF, 0x200000, M22):
        for O in (0, 0x7FFFF, 0x80000, M20):
            for qv in EXT8[:4]:
                for b in range(8):
                    for am in (0, 1):
                        pts.append((S, 4095, O, inp(am=am, se=1, sub=b & 1, qi=qv, ki=0xFF, bs=b,
                                                    ae=1, v=0xFF, W=255, first=b & 2 and 1, sel=0)))
    for _ in range(nrand):
        pts.append((rnd.randrange(1 << 22), rnd.randrange(1 << 12), rnd.randrange(1 << 20),
                    inp(am=rnd.randrange(2), load=int(rnd.random() < 0.1), sub=rnd.randrange(2),
                        M=rnd.randrange(1 << 22), se=rnd.randrange(2), qi=rnd.randrange(256),
                        ki=rnd.randrange(256), first=rnd.randrange(2), ae=rnd.randrange(2),
                        W=rnd.randrange(256), sel=rnd.randrange(2), v=rnd.randrange(256),
                        bs=rnd.randrange(8))))
    lines = []
    for S, L, O, i in pts:
        Sn, Ln, Tn = next_state(S, L, O, i)
        f = [i[k] for k in FIELDS] + [S, L, O, Sn, Ln, Tn]
        lines.append(" ".join(f"{x:x}" for x in f))
    text = "\n".join(lines) + "\n"
    open(path, "w").write(text)
    print(f"RESULT refpoints points={len(pts)} sha256={hashlib.sha256(text.encode()).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("selftest", "edges", "refpoints"))
    ap.add_argument("--outputs", type=int, default=8, choices=(2, 4, 8))
    ap.add_argument("--random", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.cmd == "selftest":
        sys.exit(selftest())
    if a.cmd == "edges":
        sys.exit(write_edges(a.outputs, a.random, a.seed, a.out))
    sys.exit(write_refpoints(a.random, a.seed, a.out))
